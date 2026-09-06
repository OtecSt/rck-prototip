# АГЕНТИК — ЕДИНЫЙ ДОКУМЕТ ТЕКУЩЕГО СОСТОЯНИЯ (синтез Kimi)

**Дата составления:** 2026-07-23.
**Составлено:** Kimi (новый исполнитель) по результатам полного аудита файлов (~900), постраничного чтения доктрин (~10 000 строк governance) и разбора 47 транскриптов сессий Claude Code (58 МБ, 26 апр – 24 мая).
**Статус документа:** onboarding/state-snapshot. Не канонический state (канон — `governance/STATE_REGISTRY.md`), не авторизация чего-либо. Read-only продукт: при составлении ни один существующий файл проекта не изменён.
**Для кого:** для владельца (проверить, правильно ли понят замысел) и для любого нового исполнителя.

---

## 1. ЗАМЫСЕЛ — словами владельца (из транскриптов)

> "CORE TARGET: Build the architecture and safe first implementation path for a local controlled agentic operating system that can support: Lean / TPS / Six Sigma / TOC / VSM; BPMN / process modeling; WIP / FIFO / Kanban / bottleneck logic; working capital modeling; financial-economic analysis; mathematical verification; pilot runs; evals/tests; observability; commands; skills; safety hooks." — 2 мая

> "Агентик = execution / workflow / state / artifacts / cleanup engine. Интеллектуалка = semantic / hypothesis / product-concept engine. Математик = formal verification / model-testing engine. Industrial Intelligence System = domain layer above them. Obsidian = semantic/navigation layer only. Human/operator = final authority." — 2 мая

> "Агентик is not a general autonomous agent and not a mega-brain." — 6 мая

> "MISSION: Accelerate Агентик toward Industrial Intelligence System 300% through a staged conditional workflow." — 2 мая

> «Архитектурный пакет v1 по диагностике производственного потока, высвобождению оборотного капитала и удержанию эффекта после улучшений» — 5 мая (бизнес-цель: методология/продукт для промышленных предприятий, пилотное доказательство эффекта, финансовая логика без оверклеймов)

> «Цель: довести "Агентика" до уровня самостоятельного агента (L10) без выбрасывания построенного бизнес/производственного фреймворка» — 13 мая (план пересборки)

**Синтез замысла:** Агентик — это гейтованная исполнительная система («фабрика смысла»), а не автономный мегамозг. Человек — финальная инстанция. Поверх исполнительного ядра растёт доменный слой Industrial Intelligence: диагностика производственных потоков, высвобождение оборотного капитала, удержание эффекта улучшений — с перспективой коммерческого продукта для промышленных предприятий. Конечная точка — L10: внешний intake → полный цикл производства бизнес-артефактов, оператор = наблюдатель с kill-switch.

**Принципы-столпы (ритуальная честность владельца):** "Do not overclaim"; "300% is not claimed"; "Full 600% NOT achieved and must NOT be claimed"; «Не буду маркировать stage как PASS на основании stage report. Только на основании bash verification»; «Каждый переход L→L+1 — документированный gate с явными criteria. Не метка, а functional capability, проверенная через evals».

---

## 2. АРХИТЕКТУРА — как система устроена

**Паттерн:** orchestrator-workers workflow (по классификации Anthropic «Building Effective Agents», зафиксировано в плане пересборки §2). Не мультиагентная автономия, не детерминированный workflow.

**Платформенный слой (Claude Code):**
- 5 core-субагентов (`.claude/agents/`, спеки 25 апр): **supervisor** (оркестратор, единственный писатель канона, единственный роутер), **validator** (единственный присваивает pass-статусы), **spec-architect**, **next-task-architect**, **finisher**. `specialists/` — пусто (anti-zoo правило AZ-3: субагент — последнее средство после чеклиста/шаблона/валидатора).
- 6 hooks (live с 25 апр, режим GUARD): session_start, user_prompt_submit, pre_tool_check, post_tool_validate, subagent_stop_check, stop_guard. Лог: `artifacts/logs/runtime_events.ndjson` (11 186 событий, 25 апр – 3 июн).
- 8 команд `agentik-*` и 7 advisory skills (`.claude/skills/`, 2 мая) — runbook'и/плейбуки.
- Validation suite: 11 валидаторов (`validation/run_validation_suite.sh`), severity contract PASS/WARN/PARTIAL/FAIL/CRITICAL.
- Tooling venv `.agentik_tooling_venv/` (Python 3.13.5: openpyxl, python-pptx, matplotlib, numpy) — станок BAF для xlsx/pptx.

**Контрольный слой (governance/):**
- Конституция `CLAUDE.md` (10 hard rules; permissions → hooks → governance → supervisor).
- `STATE_REGISTRY.md` — единственное каноническое состояние; пишет только supervisor через шаг 5 RUNTIME_LOOP.
- RUNTIME_LOOP: 6 шагов, один слой за итерацию, каждый шаг — legit stop point.
- HANDOFF_CONTRACT (7 полей), PASS_VALIDATION_SCHEMA (complete/partial/incomplete/blocked; unsafe_continuation; unresolved_manual_check кэпит continuation).
- ARTIFACT_FAMILY_POLICY (2739 строк, 37 семейств + forbidden; unknown = blocking).
- LESSONS_REGISTRY (11 уроков, lifecycle OBSERVED→…→ENFORCED, прямой прыжок запрещён).
- L7-субстрат: permission model (critical tier ENFORCING с 3 июня; broad tier — OBSERVE), kill-switch (сентинел `.claude/KILL_SWITCH_ACTIVE`, снятие только извне), runtime-loop oracle (dry-run, 33/33 теста), bounded-write capability (READY).

**Фабричный слой (доктрины):**
- `production_system/` (7 файлов, DESIGN_ONLY) — конституция: 25 принципов P1–P25 (P25: «фабрика не должна производить саму себя вечно»), 12 юнитов холдинга, 11-шаговый поток, Jidoka/Andon/Kaizen, 18 метрик (все NOT_IMPLEMENTED), WIP-капитал.
- `business_artifact_factory/` (8 файлов) — BAF: «принимаем любую идею акционера, классифицируем, маршрутизируем, производим, инспектируем»; 12 артефакт-линий BAF-01..12; «No route card, no production»; «No consumer, no business artifact»; MVBA; 13 quality gates QG-01..13; 15 классов несоответствия NC-01..15; Board Report обязателен и «информирует решение оператора, не авторизует».
- `production_line/` (8 спеков, 3 июня) — первый исполняемый инкремент: линия O0→O5 (Intake → BAF-01 → BAF-02 → BAF-03 → BAF-12 → QC) с гейтами G0–G5, 8 инвариантов I1–I8, andon-stop протокол.
- `knowledge_design/` (6 файлов) — KB-дизайн: иерархия авторитета L0–L8, retrieval-профили, шкалы R/I/O/S/Q. Не пилотировалась ни разу (полка); шкалы и уровни — живой словарь.
- `reference_mapping/` (6 файлов) — Reference Warehouse: 8 источников, 12 паспортов MAT, 12 рекомендаций REC, карантин-реестр. Выполненная работа, advisory.
- `prompt_factory/` — QC-контур промптов: risk-tiers, сканер дефектов, 24 класса дефектов G-D01..G-D24, 36 executable-тестов, OPERATOR_DECISION_LOG, STAGE_STATUS_BOARD, CURRENT_COWORK_CONTEXT_LOCK.

---

## 3. ЧТО РЕАЛЬНО РАБОТАЕТ (доказано файлами, не декларациями)

1. **BAF-фабрика производит.** 4 пилота «радиаторной» серии (ООО «Оренбургский радиатор» — кейс C-1 из Pilot Selection Matrix): реальные xlsx-модели (100–124 формулы), pptx board-презентации, QC-отчёты (60/60 в 1.1). Пилоты 1.3/1.4 — blind-тесты против человеческого эталона: OPERATOR_OBSERVED хронометрия + REPORTED финансы FY2021–2023. Это downstream-value proof.
2. **Хуки живы и кусаются:** 11 186 событий; 14 destructive-блокировок; 18 permission_enforce_block_critical; 3 kill_switch_active_block.
3. **Два из трёх guardrails автономии активны (3 июня):** permission-enforcement критического яруса (реальный exit 2 на protected_surface/external) и kill-switch (external-clear only — «the agent cannot un-kill itself»).
4. **Validation suite 11/11** — платформенно-нейтральный bash, работает независимо от движка.
5. **Дисциплина стадий:** 50+ стадий с отчётами, sha-frozen свидетельства, backup-ритуал, claim-vs-proof протокол.
6. **QC-контур промптов:** ни один Tier-1 промпт не запускался без скана + hostile review + явного APPROVE_FOR_LAUNCH.

## 4. ДОЛГИ (не закрыто на момент остановки)

| Долг | Факт | Статус |
|---|---|---|
| STATE_REGISTRY split (этап 01) | 5 296 строк вместо ≤500; 56 бэкапов | Не начат, реестр вырос |
| LEVEL_CONTRACTS.md + AGENTS.md (этап 02) | Файлы не существуют | Не начат |
| Skills implementation (этап 03) | Плановые 4 skills не созданы; существующие 7 advisory посчитаны достаточными | Молча снят |
| MCP excel-csv-reader (этап 04b) | Черновик, `draft_disabled`; потребность закрыл venv | Официально DEFERRED |
| «Математик» F-006 (этап 07) | Единственный unresolved CRITICAL failure; сессия не состоялась | Не начат |
| Validator v2 single-source (этап 09) | Трёхветочный валидатор на месте; DO_NOT_RUN (G-D13) | Не начат |
| L8 functional gate (этап 10) | `l8_readiness_overall: NOT_READY`; заменён выбором пути LEAN_MVP_TRIO | Заменён |
| L9/L10 runtime-loop (этап 11) | Runtime loop = oracle-симулятор, execution=false | Не начат |
| Runtime-loop execution (последний элемент LEAN_MVP_TRIO) | Не начат; первый шаг — production line v1 dry-run — подготовлен, но не запущен | **Точка остановки** |
| Гигиена | artifacts/current = 30 файлов (лимит ≤10); бэкапы scripts/validation 20–22 вместо 3; шапка STATE_REGISTRY протухла на 3 недели; README рапортует «Stage 2» | Деградировало |

## 5. ТОЧКА ОСТАНОВКИ — зафиксированная

**3 июня 2026, 23:25.** Последняя завершённая стадия: `stage_permission_enforce_critical` (PASS, 22:32; sha STATE_REGISTRY `3bd67c1b` — совпадает с фактическим, реестр не мутировал после).

**Подготовленная, но не запущенная стадия:** `prompts/baf_production_line_v1_run.md` — dry-run линии v1 по регрессионной карте `RC_RADIATOR_REGRESSION_001` (медно-радиаторный завод, FY2021–2023: CCC 101→134 дня, DIO-доминирующая заморозка кэша при росте маржи 1.78%→9.55%; «profit up, cash trapped»). Промпт ждёт операторского `APPROVE_FOR_LAUNCH: baf_production_line_v1_run` + `ROUTE_CARD=<path>`. Доказательства невыполнения: `production_line/runs/` не существует, TRACE/HALT файлов нет, скан-реестры дефектов не обновлены, DECISION_LOG без записи одобрения.

**Следующий шаг по замыслу (дорожная карта, подтверждена тремя источниками):** hostile-review runner-промпта → одобрение → dry-run O0→O5 → сверка трассы с эталоном `BAF_LINE_DRY_RUN_EXAMPLE.md` → v1.1 produce mode → Universal Intake (оркестратор) → субагенты на станциях. Roadmap жёсткий: worker #1 до оркестратора, оркестратор до субагентов (S1: flow discipline предшествует scaling).

## 6. ХРОНОЛОГИЯ РЕШЕНИЙ (из транскриптов)

- **24–25 апр:** PROJECT_SPEC → Stage 1–6: скелет, core governance, core-five агенты, settings, хуки v1.
- **26–28 апр:** 7.6–8.7 — пилоты хуков в реальных сессиях; боль: false positives, SubagentStop payload (урок «diagnostic-first»); V1_ACCEPTED_WITH_LIMITATIONS.
- **30 апр – 2 мая:** первый реальный workflow (ТЗ на модель удержания эффекта WC); Lessons Registry; 10.K Tri-System Bridge (Математик/Интеллектуалка/Obsidian); META-WORKFLOW «300%» → PARTIAL, "300% is not claimed".
- **3–6 мая:** cleanup-марафон; аборт 10.K.2A (settings drift от permission harness); 4 рецидива artifact-family gap → единая ARTIFACT_FAMILY_POLICY («close the class of problem, not add another narrow one-off patch»); Stage 10.K.3 — поворот к бизнес-пилотам; Prompt Foundry («Агентик may propose prompt candidates. Агентик may NOT approve or execute its own prompt candidates»).
- **7–10 мая:** Capability System (5 capabilities); L6 read-only оператор — закрыт 9 мая; марафон 10 мая (~25 операций: archive cycles 1–3, L7-entry.1 PASS в 19:58 UTC).
- **11–12 мая:** stages 17–23 (permission model, runtime-loop dry-run, kill-switch dry-run, bounded-write pilots); «Runtime-loop без permission checker = forbidden architecture»; «Если 17 слабый, то 18–20 будут имитировать инженерность»; пять design-стадий за день (Knowledge-Base, Reference-Mapping, Production-System-Doctrine…).
- **13 мая:** BAF-Doctrine.1 + BAF-Pilot-1.1 «300% LOAD PILOT» (PASS, 60/60). Вечером — заказан hostile-аудит («МРТ-срез системы… без сглаживания») → AUDIT_INDEPENDENT + план пересборки за одну ночь.
- **14–24 мая:** archive cycle 4 (PASS); эпопея stage_04a: FAIL (дубли ключей в каноне) → recovery FAIL (timestamp-контракт) → 2× API 403 → 2× operator halt («halting with no changes» — ноль мутаций) → PASS 24 мая. Сухие уроки: dry-run перед мутацией стал нормой; measure-then-conclude (G-D17).
- **24 мая 08:58 — последняя терминальная сессия.** Далее работа переехала в Cowork (десктоп): пилоты 1.2–1.4, pilot review, hooks recon, L8 readiness recon, permission observe→enforce, kill-switch, production line v1. Обрыв 3 июня 23:25.

## 7. КЛЮЧЕВЫЕ УРОКИ, ОБЯЗАТЕЛЬНЫЕ ДЛЯ ИСПОЛНИТЕЛЯ

- **Оператор — единственная launch-власть.** Self-issued LAUNCH_READY запрещён (G-D02). Размытое одобрение = AMBIGUOUS.
- **Claim vs proof:** верить только пере-запускаемому bash (sha256, validation suite, head/tail), не отчётам (claim-before-measure = G-D17).
- **Registration ≠ activation** (G-D03). Созданный файл ничего не активирует.
- **STATE_REGISTRY пишет только supervisor**, marker-bounded, с cmp-verified backup; перед мутацией — dry-run (норма с 20 мая).
- **Sha-дисциплина:** любое изменение sha промпта после одобрения → свежее hostile review.
- **macOS venue:** bash 3.2 (нет `declare -A`, `sha256sum` без wrapper'а); Linux PASS ≠ macOS PASS (G-D08).
- **Kill-switch снимается только внешне** (`rm .claude/KILL_SWITCH_ACTIVE` в обычном терминале); верификация НЕ создаёт сентинелы (L-VERIFY-01 — инцидент 3 июня).
- **Evidence-class дисциплина BAF:** каждое материальное число — REPORTED / FORMULA_DERIVED / FORMULA_DERIVED_FROM_SCENARIO_ASSUMPTIONS / SCENARIO_ASSUMPTION / NORMATIVE_ASSUMPTION / PLACEHOLDER_FOR_FUTURE_MEASUREMENT; неклассифицированное = andon-stop; «точный подтверждённый эффект» = overclaim = QG-09 stop.
- **P25-рамка:** каждый новый артефакт — с named downstream consumer и utilization path; «это downstream-ценность или снова фабрика?».
- **Authority-дисциплина:** «A recommendation may be smarter than the current roadmap. It still cannot override next_allowed_stage.»
- **Genchi Genbutsu:** состояние проверять по файловой системе, не только по реестру (шапка STATE_REGISTRY отстаёт от фактики).

## 8. ПАСХАЛКИ И КУЛЬТУРА (зафиксировано для истории)

«✻ Sautéed for 6m 21s» (кулинарный спиннер в pr.md); `maturity: PARTIAL_600_HARDENING` («Что значит 600%?» — аудит); «THIS IS THE MOST CRITICAL CANONICAL STATE-SYNC IN PROJECT HISTORY»; README «Stage 2 — Repo skeleton» после 50+ стадий; «balast» в официальном плане; вечный невызванный «Математик» (F-006); `update_state.sh` — живой мёртвый stub; жонглирование Opus 4.7 max ↔ Sonnet 4.6; «Bye!/See ya!» на /exit.

## 9. ПЛАТФОРМЕННАЯ НОТА (июль 2026)

Проект строился на Claude Code (терминал). Аккаунт владельца утрачен; CLI удалён; транскрипты терминальных сессий (26 апр – 24 мая) и memory сохранены локально в `~/.claude/projects/`. Cowork-сессии (24 мая – 3 июня) — на серверах Anthropic, но этот период полностью задокументирован в проекте (CONTEXT_LOCK, DECISION_LOG, отчёты). С июля 2026 исполнителем выступает Kimi: стадийные промпты читаются с диска, verification — тем же bash, хуки прогоняются вручную в точках цикла, роли субагентов эмулируются спеками из `.claude/agents/`. Методология переносима полностью; платформенная автоматика (авто-срабатывание хуков, изоляция субагентов) — эмулируется до решения о платформе для этапа runtime-loop activation.

## 10. ИСТОЧНИКИ СИНТЕЗА

Файловый аудит (4 разведки, ~900 файлов); постраничное чтение: production_system (7), BAF (8+1), production_line (8), knowledge_design (6), reference_mapping (6), контрольный слой (CLAUDE.md, SUPERVISOR, RUNTIME_LOOP, HANDOFF_CONTRACT, PASS_VALIDATION_SCHEMA, LESSONS_REGISTRY, ARTIFACT_FAMILY_POLICY, runtime_loop/permissions/recovery/bounded_write/readiness, prompt_factory целиком); транскрипты: 23 файла ранней эпохи + 11 файлов поздней эпохи из `~/.claude/projects/-Users-aleksandr-Desktop-------/`; AUDIT_INDEPENDENT__20260513.md; AGENTIK_REBUILD_PLAN__20260513.md; PROJECT_SPEC.

*Составлено честно: где знание неполно — помечено. Владелец — финальная инстанция по замыслу; этот документ ему на проверку.*
