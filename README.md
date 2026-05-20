# SCM KPI Optimizer

Streamlit-приложение для анализа транспортной SCM-сети на основе **ориентированного DAG** с KPI на рёбрах: **cost**, **time**, **risk**.

Учебный проект: генерация сети, визуализация, оптимизация маршрутов (Dijkstra), подбор сбалансированного маршрута с якорным KPI и анализ KPI.

---

## Структура проекта

```
lab-baev/
├── app.py                 # Streamlit UI (точка входа)
├── graph_generator.py     # Генерация и редактирование DAG
├── graph_visualizer.py    # Matplotlib / Plotly / Pyvis
├── path_optimizer.py      # Dijkstra, ranking, balanced path
├── kpi_analysis.py        # Отклонения KPI, рекомендации
├── report_generator.py    # Экспорт отчётов (PDF, CSV, JSON)
├── session_manager.py     # Управление session_state и JSON save/load
├── utils.py               # Общие вспомогательные функции
├── requirements.txt
├── runtime.txt            # Python version (Streamlit Cloud)
├── packages.txt           # OS packages (Streamlit Cloud)
├── assets/
├── exports/               # Экспортированные отчёты
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

### Порядок работы в приложении

1. **Граф** — сформировать DAG  
2. **Визуализация** — выбрать тип рендера, настроить параметры отображения и подсветить маршрут  
3. **Маршруты** — выполнить оптимизацию по якорному KPI и допуску  
4. **KPI** — проанализировать отклонения и рекомендации  

Сессию можно сохранить и загрузить через боковую панель (**Скачать сессию / Загрузить сессию**).

---

## Публикация в GitHub

```bash
git init   # если репозиторий еще не инициализирован
git add .
git commit -m "Add SCM KPI Optimizer Streamlit app"
git branch -M main
git remote add origin https://github.com/<username>/lab-baev.git
git push -u origin main
```

Убедитесь, что в репозитории есть: `app.py`, `requirements.txt`, все `.py` модули.

---

## Развертывание в Streamlit Cloud

1. Перейдите на [share.streamlit.io](https://share.streamlit.io) и выполните вход через GitHub.  
2. **New app** → выберите репозиторий `lab-baev`.  
3. **Main file path:** `app.py`  
4. **Branch:** `main`  
5. Нажмите **Deploy**.

Streamlit Cloud автоматически читает:

| Файл | Назначение |
|------|------------|
| `requirements.txt` | Python-зависимости |
| `runtime.txt` | Версия Python (`python-3.11`) |
| `packages.txt` | Системные пакеты (при необходимости) |

---

## Устранение неполадок

| Проблема | Решение |
|----------|---------|
| `ModuleNotFoundError` | Проверьте `requirements.txt` и пересоберите приложение в Streamlit Cloud |
| Pyvis не отображается | Используйте вкладку **Визуализация** и выберите **Plotly** или **Matplotlib** |
| Нет пути source→target | Увеличьте `edge_probability` или сформируйте граф повторно |
| Циклы в графе | Генератор гарантирует DAG; ручные рёбра только «вперёд» по номеру узла |
| Ошибка сборки в Streamlit Cloud | Убедитесь, что `runtime.txt` содержит поддерживаемую версию (`python-3.11`) |
| `Unable to locate package #` | В `packages.txt` нельзя указывать комментарии; допускаются только имена пакетов, по одному в строке |
| Большой граф — длительная оптимизация | Уменьшите число узлов или значение `edge_probability` |

---

## Итеративная разработка

Рекомендуемая последовательность этапов:

1. Структура проекта  
2. `app.py` (UI skeleton)  
3. `graph_generator.py`  
4. `graph_visualizer.py`  
5. `path_optimizer.py`  
6. `kpi_analysis.py`  
7. `session_manager.py`  
8. `report_generator.py`  
9. Интеграция в `app.py`  
10. Развертывание  

При возникновении ошибок рекомендуется использовать точечные задачи (например, «исправить только `generate_random_dag`»), а не запрашивать полную переработку проекта.

---

## Лицензия

Учебный проект. Использование осуществляется по согласованию с кафедрой или преподавателем.
