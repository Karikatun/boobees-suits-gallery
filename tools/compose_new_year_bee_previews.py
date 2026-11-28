"""Compose the winter model and fitting previews."""

from pathlib import Path

import compose_bee_sneaker_previews as preview


preview.OUTPUT = Path(__file__).resolve().parents[1] / "dist/new-year-bee"
items = [
    ("hat", "Шапочка с огоньками"), ("scarf", "Вязаный шарф"), ("sweater", "Свитер со снежинками"),
    ("sleeve-left", "Левый рукав"), ("sleeve-right", "Правый рукав"), ("abdomen", "Полосатое брюшко"),
    ("wings", "Крылья с инеем"), ("boot-left", "Левый ботинок"), ("boot-right", "Правый ботинок"),
]
preview.sheet(items, "concepts", "Новогодняя пчела", "Девять макетов для Meshy 7.1",
              "concepts.png", 3, (340, 275), alpha=True)
preview.sheet(items, "renders", "Новогодняя пчела", "Отдельные модели для семибота",
              "items.png", 3, (340, 275))
preview.sheet([
    ("stand-front", "Стойка · спереди"), ("stand-three-quarter", "Стойка · ¾"),
    ("stand-rear", "Стойка · сзади"), ("crouch-front", "Присед · спереди"),
    ("crouch-three-quarter", "Присед · ¾"), ("crouch-rear", "Присед · сзади"),
], "renders", "Новогодняя пчела на семиботе", "Стойка и присед · три ракурса",
   "assembly.png", 3, (365, 452))
preview.sheet([
    ("stand-down-three-quarter", "Стойка · вниз"), ("stand-up-three-quarter", "Стойка · вверх"),
    ("crouch-down-three-quarter", "Присед · вниз"), ("crouch-up-three-quarter", "Присед · вверх"),
], "renders", "Проверка посадки в наклонах", "Штатные позы R.E.P.O. 0.5.3",
   "tilts.png", 4, (330, 409))
