"""Public screenshot fixtures. Only used on verify_web's throwaway database."""
import json
from random import Random

from PIL import Image, ImageDraw
from sqlalchemy import text

from app.integration.demo import demo_id


def prepare_readme_capture(engine, directory):
    if engine.url.host != "127.0.0.1" or engine.url.database != "fixrate_test_browser":
        raise ValueError("The README fixture requires the isolated browser test database")
    rng = Random(674103)
    asset_code = f"VU-{rng.randrange(101, 900):03}"
    names = [f"{first} {last}" for first in ("Артём", "Роман", "Иван", "Никита", "Кирилл",
                                             "Сергей", "Михаил", "Егор", "Павел") for last in
             ("Громов", "Данилов", "Зорин", "Крылов", "Раков", "Новиков", "Родин", "Власов", "Серов")]
    rng.shuffle(names)
    site = demo_id("site")
    with engine.begin() as conn:
        conn.execute(text("UPDATE sites SET name=:name,address=:address WHERE site_id=:site"),
                     dict(site=site, name="ЖК «Липовый квартал»", address="Корпус А · техническая зона"))
        users = conn.scalars(text("SELECT user_id FROM site_memberships WHERE site_id=:site ORDER BY user_id"),
                             dict(site=site)).all()
        for user, name in zip(dict.fromkeys(users), names):
            conn.execute(text("UPDATE users SET full_name=:name WHERE user_id=:user"), dict(name=name, user=user))
        for table in ("equipment", "engineering_systems", "crews"):
            conn.execute(text(f"""UPDATE {table} SET name=regexp_replace(name, '^(demo|демо)[[:space:]—:-]*', '', 'i')
                                  WHERE site_id=:site AND name ~* '^(demo|демо)'"""), dict(site=site))
        conn.execute(text("UPDATE skills SET name=:name,code=:code WHERE skill_id=:id"),
                     dict(id=demo_id("assignment-skill"), name="Обслуживание систем вентиляции", code="HVAC-INSPECTION"))
        conn.execute(text("""UPDATE work_orders SET operation_snapshot = operation_snapshot ||
              jsonb_strip_nulls(jsonb_build_object(
                'title',regexp_replace(operation_snapshot->>'title','^(demo|демо)[[:space:]—:-]*','','i'),
                'label',NULLIF(regexp_replace(operation_snapshot->>'label','^(demo|демо)[[:space:]—:-]*','','i'),''),
                'code',regexp_replace(operation_snapshot->>'code','^DEMO[-: ]*','TO-','i')))
              WHERE site_id=:site"""), dict(site=site))
        for key, code, title, label in (
            ("runtime", "ВУ-1.4", "Очистка защитной решётки вентилятора",
             "Очистить решётку вентилятора, осмотреть крепёж и приложить фотографии до и после."),
            ("assignment", "ВУ-1.6", "Проверка креплений приточной установки",
             "Осмотреть крепления и виброизоляторы приточной установки. Требуется два исполнителя."),
        ):
            conn.execute(text("""UPDATE operation_templates SET code=:code,title=:title,description=:label
                                 WHERE operation_template_id=:id"""),
                         dict(id=demo_id(f"{key}-operation"), code=code, title=title, label=label))
            conn.execute(text("""UPDATE work_orders SET operation_snapshot=operation_snapshot ||
                                  jsonb_build_object('title',CAST(:title AS text),'code',CAST(:code AS text),
                                      'label',CAST(:label AS text),'instructions',CAST(:label AS text))
                                 WHERE work_order_id=:id"""),
                         dict(id=demo_id(f"{key}-order"), code=code, title=title, label=label))
        conn.execute(text("""UPDATE work_orders SET operation_snapshot=operation_snapshot ||
                              '{"title":"Осмотр воздуховода","code":"ВУ-1.2","label":"Осмотреть соединения воздуховода."}'::jsonb
                             WHERE work_order_id=:id"""), dict(id=demo_id("assignment-busy-order")))
        conn.execute(text("""UPDATE equipment SET asset_code=:code,name=:name,location=:location
                             WHERE equipment_id=:id"""), dict(id=demo_id("equipment-2"), code=asset_code,
                             name="Вытяжная установка корпуса А", location="Технический этаж, секция 2"))
        conn.execute(text("""UPDATE equipment SET asset_code=:code,name=:name,location=:location
                             WHERE equipment_id=:id"""), dict(id=demo_id("assignment-equipment"), code="PU-204",
                             name="Приточная установка секции 2", location="Вентиляционная камера, секция 2"))
        conn.execute(text("""UPDATE maintenance_rules SET source_text=:description
                             WHERE maintenance_rule_id IN (:runtime,:assignment)"""),
                     dict(description="Плановое техническое обслуживание", runtime=demo_id("runtime-rule"),
                          assignment=demo_id("assignment-rule")))

    directory.mkdir()
    (directory / "fixture.json").write_text(
        json.dumps({"assetCode": asset_code, "assetName": "Вытяжная установка корпуса А"}, ensure_ascii=False),
        encoding="utf-8")
    for phase in ("before", "after"):
        image = Image.new("RGB", (900, 560), (55, 64, 69))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((73, 63, 827, 497), radius=26, fill=(111, 123, 125), outline=(173, 180, 177), width=5)
        draw.rounded_rectangle((132, 111, 768, 449), radius=15, fill=(35, 42, 43), outline=(190, 193, 183), width=8)
        for y in range(133, 438, 28):
            draw.rounded_rectangle((147, y, 753, y + 15), radius=4, fill=(93, 111, 116))
            draw.line((153, y + 3, 747, y + 3), fill=(160, 170, 169), width=2)
        for x in (101, 799):
            for y in (91, 469):
                draw.ellipse((x-8, y-8, x+8, y+8), fill=(195, 200, 196), outline=(44, 46, 44), width=2)
                draw.line((x-4,y-4,x+4,y+4),fill=(68,73,72),width=2)
        if phase == "before":
            for _ in range(420):
                x, y = rng.randrange(150,750), rng.randrange(134,433)
                radius = rng.randrange(1,5)
                draw.ellipse((x,y,x+radius,y+radius), fill=(139, 128, 106))
        image.save(directory / f"{phase}.jpg", quality=89)
