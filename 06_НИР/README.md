# Исходный код НИР

| Компонент | Назначение | Состояние |
|---|---|---|
| [Шум](src/texgen/noise/README.md) | CPU, периодическая карта высот | Ядро и CLI реализованы |
| [Генерация и апскейл](src/texgen/generation/README.md) | GPU, генерация albedo по карте и тексту | Запланирован |
| [PBR](src/texgen/pbr/README.md) | Расчёт карт материала | Запланирован |

Подготовка обучающей выборки вынесена в `texgen.dataset`. В первом опыте компоненты конвейера вызываются из ноутбука.

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

## Подготовка выборки ambientCG

В каталоге с локальными картами создайте CSV в UTF-8 с заголовком:

```csv
material_id,group_id,category,license,source_url,color,caption
```

Укажите ID исходного материала, общую группу для вариантов одной поверхности, категорию, проверенную лицензию, ссылку вида `https://ambientcg.com/view?id=ID`, относительный путь к RGB-карте Color и проверенную английскую подпись. HDRI, декали и рендеры исключаются при составлении каталога. Исходную `metadata.jsonl` зеркала нужно предварительно сопоставить с файлами карт.

```powershell
python -m texgen.dataset data/catalog.csv data/ambientcg-512 --limit 400 --seed 42
```

Скрипт отбирает материалы CC0 по категориям, проверяет точные дубли RGB и уменьшает полные плитки до 512×512. Разбиение фиксируется по группам внутри категории. Для каждой категории нужны минимум три группы. Доли 80/10/10 приблизительны, особенно при разном размере групп. Результат — каталоги train, validation и test и единый manifest.jsonl с подписями, источниками и контрольными суммами исходных RGB-данных.
