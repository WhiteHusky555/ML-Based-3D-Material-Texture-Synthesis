# Исходный код НИР

Код конвейера находится в `src/texgen/`. Модуль `texgen.noise` рассчитывает карты шума на CPU. Его функцию `generate` можно вызывать из ноутбука и из будущего обработчика FastAPI.

```python
from texgen.noise import generate

height = generate("combined", size=512, cells=8, seed=42)
```

Для запуска из папки `06_НИР` в PowerShell используйте окружение с NumPy, Numba и Pillow:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m unittest discover -s tests -v
python -m texgen.noise --output examples/noise
```

В ноутбуке добавьте путь к каталогу `src` в `sys.path` перед первым импортом. Тесты находятся в `tests/`, примеры карт — в `examples/noise/`, план и требования — в `docs/`.
