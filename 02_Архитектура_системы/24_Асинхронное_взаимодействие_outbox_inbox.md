# Асинхронное взаимодействие через брокер: Transactional Outbox и Inbox (исследование 13.11.2026)

Требование пользователя от 13.11.2026: «все запросы должны быть асинхронные через брокер сообщений (желательно) + можно попробовать inbox outbox паттерны применить». Там же вопрос: «может всё-таки Kafka вместо RabbitMQ?»
Связано: [12](12_Kubernetes_и_асинхронность.md) (асинхронность), [17](17_Предложение_внедрения_BFF.md) (BFF), [21](21_RabbitMQ_или_Kafka.md) (выбор брокера), [22](22_Kotlin_и_Ktor_для_администрирования.md), [23](23_Vaadin_для_интерфейса.md).

## 1. Коротко
- **Брокер остаётся RabbitMQ.** Новое требование не меняет решение от 02.11.2026 ([21](21_RabbitMQ_или_Kafka.md)):
  - outbox и inbox живут в базах сервисов и от брокера не зависят;
  - Celery на Kafka работает только с одним воркером;
  - запрос-ответ в RabbitMQ встроен (direct reply-to), в Kafka его собирают из темы ответов и идентификатора корреляции.
  
  Сильные стороны Kafka — хранение и повторное чтение событий, «родной» Debezium — системе пока не нужны. Понадобится история событий — в том же RabbitMQ есть Streams.
- **Между сервисами — только асинхронно.** Команды и события идут через RabbitMQ.
  - Отправитель с базой пишет сообщение в таблицу **outbox** той же транзакцией, что и изменение данных. Отдельный процесс-ретранслятор публикует его с подтверждением брокера.
  - Получатель записывает идентификатор сообщения в таблицу **inbox** той же транзакцией, что и результат обработки. Повтор сообщения второго эффекта не даёт.
- **Синхронными (HTTP) рекомендую оставить два вида запросов:** чтение для экрана (ответ нужен сейчас) и аутентификацию (`login`, `refresh`, `logout`, `verify`).
  - Запрос-ответ через брокер — то же ожидание, только с лишним переходом. Брокер становится точкой отказа для каждого экрана.
  - Руководство RabbitMQ советует без необходимости RPC не использовать.
  - Мгновенный отзыв доступа сохраняется: `verify` без кэша на каждый запрос.
- **Цена:**
  - доставка «хотя бы один раз» — каждый потребитель обязан быть идемпотентным;
  - в каждой базе две служебные таблицы и ретранслятор;
  - итог команды клиент узнаёт позже: `202`, затем событие по WebSocket (генератор) или server push (Vaadin).

## 2. Что проверено
| Тема | Что выяснено | Источник |
|---|---|---|
| Transactional Outbox | Сообщение сохраняется в таблицу outbox той же транзакцией, что и бизнес-данные; отдельный процесс передаёт его брокеру. Гарантия — «хотя бы один раз»: ретранслятор может упасть после отправки, но до отметки, и отправит снова | microservices.io |
| Способы ретрансляции | **Опрос таблицы** (polling publisher) работает с любой SQL-БД, но порядок соблюдать сложнее. **Чтение журнала транзакций** (transaction log tailing; в PostgreSQL — WAL; инструменты Debezium, Eventuate Tram) даёт меньшую задержку и нагрузку, но требует отдельной инфраструктуры, и дубли исключить сложнее. Практический совет: начать с опроса (`FOR UPDATE SKIP LOCKED`), на CDC переходить при росте нагрузки или требований к задержке | microservices.io; A. Aleinikov |
| Debezium без Kafka | Outbox Event Router — преобразование Debezium для таблицы outbox: маршрут по полю `aggregatetype`, payload — `jsonb`. Debezium Server работает без Kafka, в нём есть приёмники `rabbitmq` и `rabbitmqstream` | документация Debezium |
| Подтверждения в RabbitMQ | Подтверждения потребителя (manual ack) и публикатора (publisher confirms) дают доставку «хотя бы один раз». При повторной отправке возможны дубли, поэтому потребители должны быть идемпотентными или отбрасывать дубли. В кворумных очередях подтверждение публикатору приходит после записи на кворум узлов; перенаправление в dead-letter может работать в режиме «хотя бы один раз» | документация RabbitMQ: Reliability, Confirms, Quorum Queues |
| Inbox, идемпотентный потребитель | Таблица обработанных сообщений с ключом по идентификатору сообщения. Запись в неё идёт той же транзакцией, что и бизнес-эффект, — потребительская пара к Outbox. Записи удаляются по сроку. «Проверить, есть ли запись, затем вставить» без уникального ключа даёт гонку — нужен уникальный ключ | Microsoft Learn (Azure Architecture Center); M. Jovanović; Y. Cui; BEE-10007 |
| Celery | По умолчанию сообщение подтверждается до выполнения задачи. С `acks_late` — после: если воркер упадёт, задача выполнится снова, поэтому задачи должны быть идемпотентными | документация Celery 5.7 |
| Публикация из Python | aio-pika (поверх aiormq): автопереподключение, publisher confirms, транзакции, Python 3.11+. Celery повторяет публикацию, но политика по умолчанию короткая; чтобы заметить отказ брокера, нужны подтверждения публикатора | документация aio-pika; aleksul.space |
| Блокировка строк без сырого SQL | SQLAlchemy: `with_for_update(skip_locked=True)`. Exposed: `forUpdate(ForUpdateOption.PostgreSQL.ForUpdate(MODE.SKIP_LOCKED))`. Несколько реплик ретранслятора берут разные строки | документация SQLAlchemy; исходный код и issue #837 Exposed |
| Outbox в Spring | Spring Modulith: реестр публикаций событий (Event Publication Registry) пишет запись той же транзакцией и после успешной обработки отмечает её завершённой. Неудачные публикации отправляются повторно, в том числе после перезапуска. Внешняя публикация — артефакты `spring-modulith-events-amqp` (RabbitMQ), `-kafka`, `-jms` и другие | документация Spring Modulith |
| Запрос-ответ | **RabbitMQ:** direct reply-to — псевдоочередь `amq.rabbitmq.reply-to`, ответ приходит без отдельной очереди; потребитель ответов работает без подтверждений. Учебник RabbitMQ: «если сомневаетесь — избегайте RPC», лучше асинхронный конвейер. **Kafka:** `ReplyingKafkaTemplate` (Spring) — тема ответов и заголовок с идентификатором корреляции | документация RabbitMQ; Spring for Apache Kafka |

Не проверял: какая версия Spring Modulith совместима со Spring Boot 4; задержку опроса outbox под нагрузкой — интервал выбрать по замеру.

## 3. Kafka вместо RabbitMQ?
Решение 02.11.2026 ([21](21_RabbitMQ_или_Kafka.md)) принималось для очередей задач. Сравнил заново с учётом outbox/inbox и принципа «всё через брокер».

| Требование | RabbitMQ | Kafka |
|---|---|---|
| Outbox, inbox | одинаково: живут в базах сервисов | то же; транзакции Kafka не охватывают нашу PostgreSQL, так что inbox всё равно нужен |
| CDC-ретранслятор (позже) | Debezium Server с приёмником `rabbitmq` | основной путь Debezium (Kafka Connect) — **плюс Kafka** |
| Запрос-ответ | встроен: direct reply-to | собирается из темы ответов и корреляции; готовое решение — только в Spring |
| Очередь задач Celery для GPU | брокер по умолчанию | только один воркер — конвейер не запустить ([21](21_RabbitMQ_или_Kafka.md)) |
| Приоритет премиума | приоритеты и отдельные очереди | приоритетов нет |
| История событий, повторное чтение | Streams в том же брокере | основное назначение — **плюс Kafka** |
| Управляемый сервис в Selectel | нет, только в кластере | есть — **плюс Kafka** |
| Kafka для событий + RabbitMQ для задач | — | эксплуатации вдвое больше; при «десятках задач в минуту» не окупается |

**Вывод:** остаёмся на RabbitMQ. Kafka стоит рассматривать, только если появится требование хранить и перечитывать поток событий (аналитика по событиям, event sourcing). И тогда — как журнал рядом с RabbitMQ, а не вместо брокера задач.

## 4. Какие взаимодействия куда
Принцип: команды (меняют состояние) и события — через брокер; чтение и аутентификация — синхронно.

| Взаимодействие | Сейчас | Предлагаю | Гарантии |
|---|---|---|---|
| Браузер → BFF | HTTP, WebSocket | без изменений | — |
| BFF → сервис пользователей: `login`, `refresh`, `logout`, `verify` | HTTP | **HTTP** (исключение) | `verify` без кэша — мгновенный отзыв |
| BFF → сервисы: чтение для экранов (`/bff/me`, генератор, история, 3D-просмотр, отчёты персонала) | HTTP | **HTTP** | только чтение, повтор безопасен |
| web-bff → процедурный сервис (превью шума), → ассистент (подсказки) | HTTP | **HTTP**: ответ нужен сразу, повтор безопасен | — |
| web-bff → API-сервис: создать материал, экспорт, публикация и копирование цепочки | HTTP, `202` | **команда в RabbitMQ**. Id задачи (он же ключ идемпотентности) генерирует BFF и сразу отвечает `202`; итог — по WebSocket | своей БД у BFF нет — публикация с подтверждением брокера; не подтвердилось — ошибка клиенту, повтор с тем же ключом. В API-сервисе — inbox |
| BFF → сервис пользователей: регистрация, подписка, отмена | HTTP | **HTTP** по принятому решению. Регистрация относится к аутентификации, операции подписки используют платёжный API | — |
| staff-ui → владельцы данных: блокировка, тариф, роли, пресеты, версии модели | HTTP | **команда в RabbitMQ**; итог приходит событием, Vaadin показывает его через `@Push` | подтверждение брокера; inbox у владельца |
| API-сервис → конвейер (Celery-цепочка) | запись задачи и постановка цепочки — две записи без общей транзакции | **outbox**: задача и сообщение в одной транзакции, цепочку ставит ретранслятор | `acks_late`, ключи S3 по id задачи |
| Воркеры → события этапов `job.<id>.<stage>` | RabbitMQ | без изменений: у воркеров нет БД, публикация с подтверждением | API-сервис пишет событие идемпотентно по паре (задача, этап) |
| API-сервис → сервис пользователей: учёт использования (`POST /internal/usage`) | HTTP | **событие** `job.completed` / `hint.used` через outbox | inbox: одно списание на задачу |
| Права тарифа для API-сервиса (`GET /internal/plans/{plan}`) | HTTP | **локальная копия** в API-сервисе, обновляется событием `plan.changed` | тариф пользователя по-прежнему приходит в `X-User-Plan` от `verify` |
| Сервис пользователей → письма | очередь | outbox → очередь писем | inbox: одно письмо на событие |
| Платёжная система → сервис пользователей (webhook) | HTTP | HTTP на входе + **inbox** по идентификатору события провайдера | повтор webhook не продлит подписку дважды |
| Сервисы → журнал аудита (admin-service) | — | **событие** через outbox | inbox |
| admin-service → `preset.changed`, `model_version.published` | — | **событие** через outbox | API-сервис сбрасывает кэш, GPU-воркеры подгружают веса — идемпотентно по номеру версии |

## 5. Как это устроено
### Таблица outbox
Есть в схеме каждого сервиса с БД (`users`, `core`, `admin`):
- `id` — UUID, он же `message_id`;
- `aggregate_type`, `aggregate_id`, `type`;
- `payload` — `jsonb`;
- `created_at`;
- `published_at` — пусто, пока сообщение не отправлено.

Создаётся миграцией: Alembic в Python-сервисах, Flyway в admin-service.

### Ретранслятор
- Отдельный процесс из того же образа: Deployment с 1–2 репликами.
- Цикл:
  1. взять пачку неотправленных строк с блокировкой `FOR UPDATE SKIP LOCKED`, по порядку `created_at`;
  2. опубликовать с publisher confirms, `message_id` = `id`;
  3. отметить `published_at`.
- Если процесс упал между публикацией и отметкой, сообщение уйдёт повторно — это и есть «хотя бы один раз».
- Отправленные строки удаляет CronJob через N дней.

### Таблица inbox
Есть у каждого потребителя с БД. Первичный ключ — пара `message_id` + `consumer`, плюс поле `processed_at`.
- Одна транзакция: вставить запись → выполнить действие → commit → `ack`.
- Нарушение ключа означает дубль: сразу `ack`, ничего не делать.
- Ошибка → `nack`. Когда исчерпан лимит доставок кворумной очереди, сообщение уходит в dead-letter-очередь: разбор вручную и алерт.

### Порядок сообщений
Полного порядка нет: реплик ретранслятора несколько, возможны повторы. Где порядок важен (статусы задачи), потребитель сравнивает этап или версию и не откатывает состояние назад.

### Наш стек
| Где | Outbox | Публикация | Inbox |
|---|---|---|---|
| Python-сервисы (API, пользователи) | SQLAlchemy async, та же сессия | aio-pika с publisher confirms; Celery-цепочку ставит ретранслятор | SQLAlchemy, уникальный ключ |
| admin-service (Ktor) | Exposed DSL, та же транзакция | `amqp-client` с подтверждениями | Exposed |
| staff-ui (Vaadin, Spring Boot 4) | своей БД нет — outbox не нужен | Spring AMQP с подтверждениями | — (итог получает событием) |
| web-bff | своей БД нет | aio-pika с подтверждениями | — |
| Воркеры Celery | БД нет | события этапов с подтверждениями | идемпотентность по ключам S3 |

Если у staff-ui появится своя БД, готовый outbox даёт Spring Modulith (реестр публикаций и `spring-modulith-events-amqp`).

### Почему не CDC сразу
Опрос не требует новых компонентов. Debezium добавляет Debezium Server, логическую репликацию и слот репликации в каждой БД. Переходить на Debezium Server с приёмником `rabbitmq` стоит, когда опрос станет узким местом. Таблица outbox в описанном формате для этого подходит (Outbox Event Router).

## 6. Мгновенный отзыв доступа без синхронного `verify`?
| Вариант | Как работает | Когда действует отзыв | Вывод |
|---|---|---|---|
| `verify` по HTTP без кэша (сейчас) | BFF на каждый запрос спрашивает сервис пользователей | сразу | **оставить** |
| `verify` через RabbitMQ (direct reply-to) | то же, но запрос-ответ через брокер | сразу | лишний переход; упал брокер — не работает ни один экран |
| Событие `access.revoked` → BFF удаляет сеансы | сервис пользователей публикует через outbox | после доставки события; если потребитель отстаёт — ещё позже | требованию «сразу» не отвечает; годится только **в дополнение** к `verify` |

## 7. Что поменяется при принятии
- **Архитектура:**
  - README — принцип и ретрансляторы на схеме;
  - [03](03_API-сервис_оркестратор.md) — outbox для задач, inbox для команд;
  - [09](09_Сервис_пользователей_и_тарифы.md) — учёт использования и права тарифа событиями, inbox для webhook;
  - [10](10_Инфраструктура.md) — обменники, очереди, dead-letter;
  - [12](12_Kubernetes_и_асинхронность.md) — раздел про outbox/inbox и Deployment ретрансляторов;
  - [17](17_Предложение_внедрения_BFF.md) — команды BFF через брокер;
  - [22](22_Kotlin_и_Ktor_для_администрирования.md), [23](23_Vaadin_для_интерфейса.md) — staff-ui отправляет команды через брокер;
  - [11](11_Решения_и_вопросы.md).
- **ЛР5–ЛР6:** вызовы между классами разных сервисов становятся асинхронными сообщениями (`asynchCall`, генератор их уже поддерживает); в документировании сообщений указывается обмен RabbitMQ.
- **ЛР7–ЛР8:** компонент ретранслятора outbox в каждом сервисе с БД, Deployment ретрансляторов на узлах.

## 8. Решение (13.11.2026)
1. Граница: команды и события — через брокер; чтение для экранов и аутентификация — HTTP.
2. Регистрация и подписка — HTTP.
3. Ретранслятор — опрос таблицы outbox (`SKIP LOCKED`); Debezium — когда опрос станет узким местом.
4. Брокер — RabbitMQ.

## Источники (дата обращения 13.11.2026)
- Richardson C. Pattern: Transactional outbox — https://microservices.io/patterns/data/transactional-outbox.html
- Richardson C. Pattern: Polling publisher — https://microservices.io/patterns/data/polling-publisher.html ; Pattern: Transaction log tailing — https://microservices.io/patterns/data/transaction-log-tailing.html
- Aleinikov A. Transactional Outbox Pattern — https://www.alekseialeinikov.com/en/blog/topics/architecture/transactional-outbox-pattern
- Debezium. Outbox Event Router — https://debezium.io/documentation/reference/stable/transformations/outbox-event-router.html ; Debezium Server — https://debezium.io/documentation/reference/stable/operations/debezium-server.html
- RabbitMQ. Reliability Guide — https://www.rabbitmq.com/docs/reliability ; Consumer Acknowledgements and Publisher Confirms — https://www.rabbitmq.com/docs/confirms ; Quorum Queues — https://www.rabbitmq.com/docs/quorum-queues
- RabbitMQ. Direct Reply-to — https://www.rabbitmq.com/docs/direct-reply-to ; Tutorial six: RPC — https://www.rabbitmq.com/tutorials/tutorial-six-python
- Microsoft Learn. Idempotent Consumer pattern — https://learn.microsoft.com/en-us/azure/architecture/patterns/idempotent-consumer
- Jovanović M. Implementing the Inbox Pattern for Reliable Message Consumption — https://milanjovanovic.tech/blog/implementing-the-inbox-pattern-for-reliable-message-consumption
- Cui Y. The inbox & outbox patterns for reliable event processing — https://newsletter.theburningmonk.com/posts/the-inbox-outbox-patterns-for-reliable-event-processing
- Backend Engineering Essentials. BEE-10007 Idempotent message processing — https://alivedise.github.io/backend-engineering-essentials/messaging/idempotent-message-processing
- Celery 5.7. Tasks (`acks_late`) — https://docs.celeryq.dev/en/stable/userguide/tasks.html
- aio-pika. Documentation — https://docs.aio-pika.com
- Aleksul. Choosing a Python task queue library in 2026 — https://aleksul.space/posts/choosing-python-task-queue-library
- SQLAlchemy 2.0. Selectables (`with_for_update`) — https://docs.sqlalchemy.org/en/20/core/selectable.html
- JetBrains Exposed. ForUpdateOption.kt — https://github.com/JetBrains/Exposed/blob/0.59.0/exposed-core/src/main/kotlin/org/jetbrains/exposed/sql/vendors/ForUpdateOption.kt ; issue #837 «select for update query» — https://github.com/JetBrains/Exposed/issues/837
- Spring Modulith. Working with Application Events — https://docs.spring.io/spring-modulith/reference/events.html
- Spring for Apache Kafka. Reference (`ReplyingKafkaTemplate`) — https://docs.spring.io/spring-kafka/docs/2.8.11/reference/html
