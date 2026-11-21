# Периодический шум

```python
from texgen.noise import generate

height = generate("combined", size=512, cells=8, seed=42)
```

`generate` возвращает массив NumPy формы `(size, size)` со значениями от 0 до 1. Расчёт выполняется на CPU с Numba.

| Параметр | Допустимые значения |
|---|---|
| `kind` | `perlin`, `voronoi`, `combined` |
| `size` | Сторона плитки в пикселях, целое от 2 до 4096 |
| `cells` | Число ячеек по стороне, целое от 2 до 128 |
| `seed` | Целое число от 0 |

## Экспорт PNG

Из каталога `06_НИР`:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m texgen.noise --output examples/noise
```

Для каждого вида шума команда записывает 16-битную карту высот `<kind>.png` и 8-битное превью `<kind>_2x2.png`. Для визуальной проверки стыков откройте превью.
