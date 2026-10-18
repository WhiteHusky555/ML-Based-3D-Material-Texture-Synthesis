# Утилиты «картинка → PBR-карты»

Эти сервисы не генерируют текстуру по тексту, а считают PBR-карты из готовой картинки. Аналоги нашего **PBR-сервиса** (этап 4 конвейера).
Дата сведений: 14.10.2026.

## AITextured — Free PBR Texture Generator
- **Сайт:** https://aitextured.com/pbr-texture-generator
- Из бесшовной PNG/JPG/WEBP считает **Normal, Roughness, Height, AO, Metallic**, по желанию упаковывает в одну текстуру **ORM**.
- Настройки: сила нормалей, контраст шероховатости, интенсивность AO.
- Скачивание ZIP; отдельный «engine mapper» для упаковки под **Unreal (ORM)** и **Unity**.
- Обработка на сервере, без установки.
- **Для ВКР:** подтверждает наш набор карт и упаковку ORM для Unreal; параметры (сила нормалей, контраст) — те же, что у нас в настройках PBR.

## 3D AI Studio — PBR Map Generator
- **Сайт:** https://www.3daistudio.com/Tools/PBRMapGenerator
- Картинка → карты normal, roughness, height, depth, metallic (ИИ, «PBR Extract AI»).
- Оплата кредитами (10 кредитов за изображение на момент сбора).
- В том же сервисе: Seamless Texture Generator, AI Material Generator, 3D Model Texture Generator.

## Sorceress — Material Forge
- **Статья:** https://sorceress.games/blog/ai-pbr-texture-generator-one-photo-to-game-ready-textures
- В браузере: описание текстом («weathered cobblestone street, mossy, ambient damp») или фото-референс.
- Сначала бесшовный albedo через выбранную модель изображений (по умолчанию Nano Banana 2; также GPT Image 2, Seedream 5 Lite, Flux 2 Pro, Z-Image Turbo, Grok Imagine — по данным статьи от 09.05.2026), затем полный стек карт.
- В статье PBR-материал 2026 года описан как стек из шести карт: albedo, normal, roughness, metallic, AO, emissive.
- **Для ВКР:** пример «заменяемого провайдера» модели генерации — та же идея, что в нашей архитектуре (интерфейс провайдера в сервисе генерации).

## Общий вывод
Расчёт PBR-карт из цветовой текстуры — устоявшаяся практика, её делают даже бесплатные веб-утилиты. Поэтому в ВКР PBR-сервис — **свой код по известным формулам**, без нейросети, а основной вклад — в бесшовности и связке с процедурной картой высот (рельеф берётся из шума, а не угадывается по цвету).
