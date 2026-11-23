"""Локальный комплект SD 1.5 и ControlNet в формате Diffusers."""
def load(path):
    import torch
    from diffusers import ControlNetModel, StableDiffusionControlNetPipeline

    options = dict(local_files_only=True, use_safetensors=True, torch_dtype=torch.float16)
    control = ControlNetModel.from_pretrained(path / "controlnet", **options)
    pipe = StableDiffusionControlNetPipeline.from_pretrained(path / "base", controlnet=control,
                                                            **options).to("cuda")
    adapter = path / "adapter" / "pytorch_lora_weights.safetensors"
    if adapter.is_file():
        pipe.load_lora_weights(str(adapter.parent), weight_name=adapter.name, local_files_only=True)

    def infer(prompt, height, seed, steps=25):
        rng = torch.Generator(device="cuda").manual_seed(seed)
        return pipe(prompt=prompt, image=height, height=height.height, width=height.width,
                    generator=rng, num_inference_steps=steps).images[0]

    from PIL import Image
    infer("material", Image.new("RGB", (512, 512), "gray"), 0, steps=1)
    return infer
