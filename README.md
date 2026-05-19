# SCM KPI Optimizer

Streamlit-приложение для анализа транспортной SCM-сети на основе **ориентированного DAG** с KPI на рёбрах: **cost**, **time**, **risk**.

Курсовой проект: генерация сети, визуализация, оптимизация маршрутов (Dijkstra), сбалансированный путь с anchor KPI, KPI-аналитика и экспорт отчётов (PDF / CSV / JSON).

---

## Структура проекта

```
lab-baev/
├── app.py                 # Streamlit UI (точка входа)
├── graph_generator.py     # Генерация и редактирование DAG
├── graph_visualizer.py    # Matplotlib / Plotly / Pyvis
├── path_optimizer.py      # Dijkstra, ranking, balanced path
├── kpi_analysis.py        # Отклонения KPI, рекомендации
├── report_generator.py    # PDF, CSV, JSON export
├── session_manager.py     # session_state + JSON save/load
├── utils.py               # Общие хелперы
├── requirements.txt
├── runtime.txt            # Python version (Streamlit Cloud)
├── packages.txt           # OS packages (Streamlit Cloud)
├── assets/
├── exports/               # Сгенерированные отчёты
├── temp/                  # Временные файлы (PNG и т.д.)
└── README.md
```

---

## requirements.txt

```
streamlit>=1.32.0,<2.0.0
networkx>=3.2,<4.0
matplotlib>=3.8,<4.0
plotly>=5.18,<6.0
pandas>=2.1,<3.0
numpy>=1.26,<3.0
reportlab>=4.0,<5.0
pyvis>=0.3.2,<1.0
```

---

## Локальный запуск

```bash
# 1. Клонировать репозиторий
git clone https://github.com/<your-org>/lab-baev.git
cd lab-baev

# 2. Виртуальное окружение (рекомендуется)
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

# 3. Зависимости
pip install -r requirements.txt

# 4. Запуск
streamlit run app.py
```

Приложение откроется в браузере (обычно `http://localhost:8501`).

### Workflow в приложении

1. **Graph Setup** — сгенерировать DAG  
2. **Visualization** — выбрать backend и подсветить путь  
3. **Optimization** — anchor KPI + relaxation → balanced path  
4. **KPI Analysis** — отклонения и рекомендации  
5. **Reports & Export** — PDF / CSV / JSON / PNG  

Сессию можно сохранить и загрузить через sidebar (**Download / Upload session JSON**).

---

## Деплой на GitHub

```bash
git init   # если ещё не инициализирован
git add .
git commit -m "Add SCM KPI Optimizer Streamlit app"
git branch -M main
git remote add origin https://github.com/<username>/lab-baev.git
git push -u origin main
```

Убедитесь, что в репозитории есть: `app.py`, `requirements.txt`, все `.py` модули.

---

## Деплой на Streamlit Cloud

1. Зайдите на [share.streamlit.io](https://share.streamlit.io) и войдите через GitHub.  
2. **New app** → выберите репозиторий `lab-baev`.  
3. **Main file path:** `app.py`  
4. **Branch:** `main`  
5. Deploy.

Streamlit Cloud автоматически читает:

| Файл | Назначение |
|------|------------|
| `requirements.txt` | Python-зависимости |
| `runtime.txt` | Версия Python (`python-3.11`) |
| `packages.txt` | Системные пакеты (при необходимости) |

---

## Troubleshooting

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError` | Проверьте `requirements.txt`, пересоберите app на Streamlit Cloud |
| Pyvis не отображается | Используйте вкладку Visualization → backend **Plotly** или **Matplotlib** |
| Нет пути source→target | Увеличьте `edge_probability` или перегенерируйте граф; проверьте узлы в sidebar |
| PDF пустой / ошибка | Сначала выполните **Optimization** и **KPI Analysis**, затем **Generate PDF** |
| Циклы в графе | Генератор гарантирует DAG; ручные рёбра только «вперёд» по номеру узла |
| Streamlit Cloud build fail | Убедитесь, что `runtime.txt` содержит поддерживаемую версию (`python-3.11`) |
| `Unable to locate package #` | В `packages.txt` **нельзя** писать комментарии — только имена пакетов, по одному на строку. Если apt-пакеты не нужны — оставьте файл пустым |
| Большой граф — долгая оптимизация | Уменьшите число узлов или `edge_probability` |

---

## Итеративная разработка (vibe-coding)

Рекомендуемый порядок промптов:

1. Структура проекта  
2. `app.py` (UI skeleton)  
3. `graph_generator.py`  
4. `graph_visualizer.py`  
5. `path_optimizer.py`  
6. `kpi_analysis.py`  
7. `session_manager.py`  
8. `report_generator.py`  
9. Интеграция в `app.py`  
10. Deploy  

При ошибках — **точечные промпты** («исправь только `generate_random_dag`»), а не «перепиши всё».

---

## Лицензия

Учебный проект. Используйте по согласованию с кафедрой / преподавателем.
