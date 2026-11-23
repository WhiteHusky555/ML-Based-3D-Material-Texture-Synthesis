"""Контрольная серия после пилота. Выполняется в GPU-окружении Kaggle."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image

from texgen.metrics import cell_edges, measure
from verify_pilot import verify


def generate(run, output, protocol_path, manifest):
    import torch
    from diffusers import ControlNetModel, DDIMScheduler, StableDiffusionControlNetPipeline

    models = verify(run, manifest)
    protocol = json.loads(protocol_path.read_text(encoding="utf8"))
    if protocol["manifest_sha256"] != hashlib.sha256(manifest.read_bytes()).hexdigest():
        raise ValueError("Разбиение контрольной серии отличается от пилота")
    if output.exists():
        raise FileExistsError(output)
    controls = []
    for c in protocol["conditions"]:
        with Image.open(protocol_path.parent / c["file"]) as im:
            rgb = im.convert("RGB")
        if hashlib.sha256(rgb.tobytes()).hexdigest() != c["sha256_rgb"]:
            raise ValueError("Контрольная карта изменилась")
        controls.append((c, rgb, cell_edges(c["size"], c["cells"], c["seed"])))
    options = dict(torch_dtype=torch.float16, variant="fp16", use_safetensors=True)
    control = ControlNetModel.from_pretrained(models["controlnet"], revision=models["controlnet_revision"], **options)
    pipe = StableDiffusionControlNetPipeline.from_pretrained(models["base"], revision=models["base_revision"],
                                                            controlnet=control, **options).to("cuda")
    if protocol["scheduler"] != "DDIM":
        raise ValueError("Проверьте scheduler контрольной серии")
    pipe.scheduler = DDIMScheduler.from_config(pipe.scheduler.config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(dir=output.parent) as tmp:
        stage = Path(tmp) / "validation"
        scores = []
        for model in ("base", "lora"):
            (stage / model).mkdir(parents=True)
            if model == "lora":
                pipe.load_lora_weights(run / "adapter", weight_name="pytorch_lora_weights.safetensors")
            for sample in protocol["samples"]:
                for cond, height, edges in controls:
                    for seed in protocol["diffusion_seeds"]:
                        result = pipe(prompt=sample["caption"], image=height, height=height.height, width=height.width,
                                      generator=torch.Generator("cuda").manual_seed(seed),
                                      num_inference_steps=protocol["inference_steps"], guidance_scale=protocol["guidance_scale"],
                                      controlnet_conditioning_scale=protocol["controlnet_conditioning_scale"])
                        if result.nsfw_content_detected and any(result.nsfw_content_detected):
                            raise ValueError("Проверка пайплайна заблокировала изображение")
                        image = result.images[0]
                        mid = sample["material_id"]
                        image.save(stage / model / f"{mid}_{cond['seed']}_{seed}.png")
                        metrics = measure(image, edges)
                        row = dict(model=model, material_id=mid, noise_seed=cond["seed"], diffusion_seed=seed)
                        for axis in ("x","y"):
                            row.update({f"{axis}_{k}": v for k,v in metrics.pop(axis).items()})
                        scores.append({**row, **metrics})
        with (stage / "metrics.csv").open("w", newline="", encoding="utf8") as f:
            writer = csv.DictWriter(f, fieldnames=list(scores[0]))
            writer.writeheader()
            writer.writerows(scores)
        (stage / "run.json").write_text(json.dumps(dict(models=models, protocol=protocol),indent=2),encoding="utf8")
        stage.rename(output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pilot", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    data = Path(__file__).resolve().parents[1] / "data"
    generate(args.pilot, args.output, data/"controlnet-validation/protocol.json", data/"ambientcg-400.jsonl")
