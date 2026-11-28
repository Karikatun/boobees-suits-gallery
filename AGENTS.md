# Работа с Boobees Suits

Эта ветка содержит исходники версии 0.5.7 для R.E.P.O. 0.5.4 на Unity 6000.3.28f1. В моде 27 предметов. У Boo-Bee их десять, у Sneaker Bee восемь, у New Year Bee девять. Для проверки внешнего вида используй игровые снимки в `images/`.

## Сборка из чистого клона

Нужны PowerShell 7 и .NET SDK 10.0.404 из `global.json`. DLL мода собирается для .NET Standard 2.1, которую поддерживает Unity Mono. Из корня репозитория выполни команду. При первом запуске нужен доступ к NuGet.org, NuGet BepInEx и Thunderstore.

```powershell
./tools/build.ps1
```

Скрипт скачивает зависимости в `.local/build-references/` и проверяет SHA-256 архивов перед извлечением DLL для компиляции. Для сборки без установки игры используются UnityEngine.Modules 6000.3.26 из NuGet BepInEx и публичные пакеты [R.E.P.O.GameLibs.Steam 0.4.4-ngd.0](https://www.nuget.org/packages/R.E.P.O.GameLibs.Steam/0.4.4-ngd.0), [BepInExPack 5.4.2305](https://thunderstore.io/c/repo/p/BepInEx/BepInExPack/v/5.4.2305/) и [REPOLib 4.5.1](https://thunderstore.io/c/repo/p/Zehs/REPOLib/v/4.5.1/).

Для проверки совместимости с точной версией игры перед выпуском используй DLL из `REPO_Data/Managed` установленной R.E.P.O. 0.5.4. Эта проверка нужна, пока публичные репозитории не содержат эталонных DLL этой версии. Укажи пути к игре и библиотекам явно.

```powershell
./tools/build.ps1 -GameRoot $gameRoot -BepInExCore "$profileRoot/BepInEx/core" -RepoLibPath $repoLibDll
```

Скрипт компилирует код из `src/`, проверяет версию сборки по `packaging/manifest.json` и создаёт `dist/BoobeesSuits-0.5.7.zip`. Для правок C# достаточно встроенных ресурсов в `src/Assets/` и `src/Icons/`. Версию проекта задаёт `src/BoobeesSuits.csproj`. Хеш сборки может зависеть от пути к исходникам. Версии загрузчика и игры, SHA-256 ZIP и результаты статической проверки записаны в [отчёте 0.5.7](checks/0.5.7/package-verification.json).

## Работа с костюмами

| Костюм | Сцена для правок в Blender 4.5.14 LTS | Ресурс в DLL |
| --- | --- | --- |
| Boo-Bee | `dist/semibot-runtime-fit/Boobees-bending-fit.blend` | `Outfit.bin.gz` |
| Sneaker Bee | `dist/bee-sneaker-set/Bee-Sneaker-Set.blend` | `Sneaker.bin.gz` |
| New Year Bee | `dist/new-year-bee/New-Year-Bee.blend` | `Winter.bin.gz` |

Проверь исходное состояние перед правкой. Команда экспортирует все три сцены в новый каталог под `.local/scene-check/`, оставляет там текстуры, иконки двух комплектов и отчёты, затем сверяет каждый архив мешей с `src/Assets/` по SHA-256.

```powershell
./tools/check-release-scenes.ps1 -Blender $blenderExe
```

Для Boo-Bee используй именно сцену с именем `Boobees-bending-fit.blend`. При проверке передачи проекта более ранняя `Boobees-runtime-fit.blend` прошла проверку креплений, но дала другой меш. После намеренной правки просмотри экспорт, перенеси изменённые ресурсы в `src/` и повтори проверку. Для альбедо Sneaker и Winter экспортёр пишет PNG, а плагин загружает JPEG. При замене цвета подготовь соответствующий JPEG с качеством 96 и субдискретизацией 4:4:4, проверь прозрачность исходника. Соответствие имён и общих текстур правой и левой сторон задано в `src/CostumeModels.cs`. Карта эмиссии шапки остаётся PNG.

Файлы `.local/semibot-preview/measure_fit.py`, `semibot-native.json` рядом с ним и `.local/cosmetic-skills/game/item-regions/matrices.tsv` — архивные входы инструментов посадки. При сверке с игрой проверяй версию в её данных. У карты слотов с подписью 0.5.3 и Steam build 26893562 фактическая версия по сериализованным данным игры — 0.5.4. Сцены содержат готовые детали. Для изменения посадки можно начинать с них без повторной генерации моделей в Meshy.

Проверки FBX используют сохранённые экспорты из каталогов `items/` и соответствующие `fit-receipt.json`. Они проверяют реимпорт, UV, текстуры и число треугольников. Проверка сцен отдельно использует шесть поз. После изменения геометрии обнови затронутые FBX и замеры. Для сравнения с фактическими мешами плагина используй проверку SHA-256 выше.

```powershell
& $blenderExe --background --python-exit-code 1 --python tools/check_bee_sneaker_exports.py
& $blenderExe --background --python-exit-code 1 --python tools/check_new_year_bee.py
```

## Где искать прежние ошибки

- Посадка, крепления, парная обувь и перекрытие ткани — [навык посадки](.agents/skills/repo-mod-cosmetic-fit/SKILL.md). В его `references/` есть карты слотов и замеры в JSON.
- Регистрация косметики, родители и совместимость слотов — [навык работы с REPOLib](.agents/skills/repo-mod-cosmetic-prefab/SKILL.md).
- Пропавшие предметы, открытые швы, наклоны и кооператив — [разбор Boobees Suits](.agents/skills/repo-mod-cosmetic-verification/references/boobees-suits-lessons.md) и [процедура проверки](.agents/skills/repo-mod-cosmetic-verification/SKILL.md). В `checks/0.5.3/` и `checks/0.5.4/` сохранены результаты предыдущих проверок посадки.
- Игровой тест — [изоляция сохранений](.agents/skills/repo-mod-test-isolation/SKILL.md). В `checks/VisibilityProbe/` лежит исходник проверочного плагина для 0.5.7. Он рассчитан на изолированную игру с тестовыми `save-fixture/MetaSave.es3` и `MetaSaveModded.es3`, проверяет регистрацию и переключение комплектов, снимает кадры и завершает игру. Успех отмечается файлом `soft-light-final/done.txt` со значением `PASS`. Проверка 0.5.7 пока ограничена сборкой и чтением метаданных. Для проверки кооператива нужны отдельные запуски хоста и клиента.
- Подготовка ZIP — [процедура упаковки](.agents/skills/repo-mod-packaging/SKILL.md).
