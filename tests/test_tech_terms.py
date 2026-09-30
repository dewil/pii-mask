"""Технология в резюме - предмет работы, а не работодатель.

На восьми живых резюме (30.09.2026) 61 маска организаций из 334 стояла на
инструментах и отраслевых терминах: hadoop, kafka, airflow, greenplum, скуд,
кхд, presale. Читать такой документ невозможно - вместо стека там метки.

Составные спаны ("курс Power Point", "поколение Python", "DDS-слой DWH")
перечислять поштучно бессмысленно: их бесконечно много. Они отсекаются по
устройству - стоп-термин плюс обычные слова вокруг него.
"""
import pytest

from pii_mask.core import Masker


def masked(text):
    return Masker(types=("ORG",), ner_org_needs_form=False).mask(text)[0]


# Строка стека из живого резюме (технологии, не ПД): ровно в такой форме
# дефект и живет. Одиночное слово NER пропускает, а в перечне на две строки
# метит половину списка организациями.
СТЕК = ("Технологии: MS Project, Jira, Kanban; BPwin, ARIS, Erwin; "
        "Oracle, MS SQL, PostgreSQL, GreenPlum,\n"
        "ClickHouse, Hadoop, Kafka, Informatica, Airflow, IBM Cognos, "
        "Power BI, Tableau; Smart\nVista, equation, СПАРК; "
        "импортозамещение; ГОСТ 34 и 19, EDIFACT.\n")


def test_the_whole_stack_line_survives():
    """Главный случай: перечень инструментов не должен превращаться в метки."""
    out = masked("Опыт работы\nВедущий аналитик\n" + СТЕК)
    for слово in ("Hadoop", "Kafka", "Informatica", "Airflow", "Tableau",
                  "GreenPlum", "ClickHouse"):
        assert слово in out, f"{слово} ушло в маску"


@pytest.mark.parametrize("термин", [
    "Hadoop", "Kafka", "Airflow", "Greenplum", "Apache NiFi", "Tableau",
    "Informatica", "Looker Studio", "SAS", "Spark", "Python",
    "СКУД", "СОУЭ", "BMS", "CCTV", "КХД", "НСИ", "БКИ", "ПДн",
    "Galileo", "Amadeus", "eNPS", "presale", "due diligence", "FMCG",
])
def test_tools_and_terms_are_not_employers(термин):
    # Перечисление через запятую - та самая форма, в которой дефект и живет:
    # одиночное слово NER пропускает, а в списке метит соседей организациями
    # (живые резюме 30.09.2026: "ClickHouse, Hadoop, Kafka, Airflow" - половина
    # списка ушла в маски).
    текст = ("Опыт работы\nВедущий инженер\n"
             f"Стек: Oracle, MS SQL, PostgreSQL, {термин}, ClickHouse, Grafana.\n")
    assert термин in masked(текст)


@pytest.mark.parametrize("спан", [
    "курс Power Point",
    "поколение Python",
    "DDS-слой DWH",
    "офлайн-NER",
    "SQL Python BigData",
])
def test_compound_spans_around_a_known_term_are_not_employers(спан):
    """Стоп-термин плюс обычные слова - все еще не место работы."""
    текст = f"Опыт работы\nВедущий аналитик\nОбучение: {спан}, практика.\n"
    assert спан in masked(текст)


def test_a_real_employer_next_to_a_term_survives():
    """Правило не должно съедать название рядом с технологией."""
    текст = ('Опыт работы\n'
             'ООО "Светопись", 02.2014 - 01.2025\n'
             'Ведущий инженер\nСтек: Kafka, Airflow.\n')
    out = masked(текст)
    assert "Светопись" not in out
    assert "Kafka" in out and "Airflow" in out


def test_term_inside_a_quoted_name_is_still_masked():
    """"ООО «Спарк»" - организация, хотя spark и технология."""
    out = masked('Работал в ООО "Спарк" два года.')
    assert "Спарк" not in out
