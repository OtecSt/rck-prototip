# -*- coding: utf-8 -*-
"""Приёмка 06.09: создать проект «приёмка-0609» на продe и наполнить
полным набором прогонов (фикстура _qa_p4_ui.py). Печатает pid."""
import copy
import json
import sys
import urllib.request
import base64

BASE = "https://201.34.132.154"
AUTH = "Basic " + base64.b64encode("рцк:H8BgJlzfjESRDv4F".encode()).decode()
PROT = "/Users/aleksandr/Desktop/Методички/ИИ-направление/Прототип"


def req(method, path, body=None):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(
        BASE + path, data=data, method=method,
        headers={"Content-Type": "application/json", "Authorization": AUTH})
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(r, timeout=60, context=ctx) as resp:
        return resp.status, json.loads(resp.read())


ЭТАЛОН = {"поток": "Поток приёмки 0609", "спрос_шт_в_период": 240,
          "доступное_время_мин": 480, "численность_чел": 5,
          "операции": [
              {"имя": "Оп1", "тц_мин": 1.25, "запас_после_шт": 2000},
              {"имя": "Оп2", "тц_мин": 1.5, "запас_после_шт": 700},
              {"имя": "Оп3", "тц_мин": 1.44, "запас_после_шт": 800}]}
СИМ_ДО = {"поток": "Поток приёмки 0609", "спрос_шт_в_период": 240,
          "доступное_время_мин": 480,
          "операции": [{"имя": "Оп1", "тц_мин": 1.25, "запас_после_шт": 0},
                       {"имя": "Оп2", "тц_мин": 2.4, "запас_после_шт": 0},
                       {"имя": "Оп3", "тц_мин": 2.2, "запас_после_шт": 0}],
          "симуляция": {"seed": 1, "прогонов": 10}}
СИМ_ПОСЛЕ = copy.deepcopy(СИМ_ДО)
СИМ_ПОСЛЕ["операции"][1]["тц_мин"] = round(2.4 * 0.8, 4)
ЭТАЛОН_OEE = {"поток": "Поток приёмки 0609", "плановое_время_мин": 480,
              "простои": {"аварии_мин": 47, "переналадка_мин": 38,
                          "микроостановки_мин": 22},
              "идеальное_тц_мин": 1.0, "выпуск_всего_шт": 350, "брак_шт": 12}
ЭТАЛОН_МЕР = {"predpriyatie": "Приёмка-0609", "uchastok": "фасовка",
              "vpp_pct": 38.7, "norma_vpp_pct": 15.0,
              "razryv": {"value": 23.7, "unit": "п.п. ВПП", "evidence": "fact"},
              "priznaki": {"простои_оборудования": True,
                           "организация_рабочих_мест": True},
              "vidy_potery": [{"nazvanie": "Ожидание"}],
              "zamery": {}}
ЭТАЛОН_SMART = {"рамка": "федеральная", "предприятие": "Приёмка-0609",
                "поток": "Поток приёмки 0609",
                "цели": [{"наименование": "Выработка", "ед": "шт/чел",
                          "текущий": 10, "целевой": 12, "срок": "2026-12-31"}]}


def main():
    # ищем существующий проект «приёмка-0609»
    _, j = req("GET", "/api/proekty")
    pid = None
    for p in j.get("proekty", []):
        if p.get("название") == "приёмка-0609":
            pid = p["id"]
            break
    if not pid:
        _, j = req("POST", "/api/proekty",
                   {"название": "приёмка-0609", "предприятие": "Приёмка-0609",
                    "поток": "Поток приёмки 0609"})
        pid = j["id"]
        print("создан проект", pid)
    else:
        print("проект уже есть:", pid)

    def сохранить(инструмент, вход, метка=None):
        body = {"id_proekta": pid, "инструмент": инструмент, "вход": вход}
        if метка:
            body["метка"] = метка
        st, j = req("POST", "/api/progony", body)
        assert j.get("ok"), f"прогон {инструмент} не сохранился: {j}"
        print(f"  сохранён {инструмент} {метка or ''}".rstrip())

    сохранить("potok_calc", ЭТАЛОН)
    сохранить("uzkie_mesta",
              json.load(open(PROT + "/данные_окз_слепой.json", encoding="utf-8")))
    сохранить("simulation", СИМ_ДО, метка="до")
    сохранить("simulation", СИМ_ПОСЛЕ, метка="после")
    сохранить("ee", json.load(open(PROT + "/данные_ээ_новохром.json",
                                   encoding="utf-8")))
    сохранить("oee", ЭТАЛОН_OEE)
    сохранить("meropriyatiya", ЭТАЛОН_МЕР)
    сохранить("smart", ЭТАЛОН_SMART)
    сохранить("protokol",
              json.load(open(PROT + "/данные_протокол_кушкуль.json",
                             encoding="utf-8")))
    print("PID=" + str(pid))


main()
