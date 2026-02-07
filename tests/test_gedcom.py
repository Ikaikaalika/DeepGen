from deepgen.services.gedcom import export_gedcom, parse_gedcom_text


SAMPLE = """0 HEAD
1 GEDC
2 VERS 5.5.1
0 @I1@ INDI
1 NAME Jane /Doe/
1 SEX F
1 BIRT
2 DATE 1 JAN 1930
1 FAMC @F1@
0 @I2@ INDI
1 NAME John /Doe/
1 SEX M
1 BIRT
2 DATE 1 JAN 1900
1 DEAT
2 DATE 1 JAN 1970
0 @I3@ INDI
1 NAME Mary /Smith/
1 SEX F
1 BIRT
2 DATE 1 JAN 1903
1 DEAT
2 DATE 1 JAN 1980
0 @F1@ FAM
1 HUSB @I2@
1 WIFE @I3@
1 CHIL @I1@
0 TRLR
"""


def test_parse_gedcom_links_parents_and_version():
    parsed = parse_gedcom_text(SAMPLE)
    assert parsed.version == "5.5.1"
    jane = [p for p in parsed.people if p.xref == "@I1@"][0]
    assert jane.father_xref == "@I2@"
    assert jane.mother_xref == "@I3@"
    assert jane.is_living is True


def test_export_gedcom_contains_required_markers():
    parsed = parse_gedcom_text(SAMPLE)
    payload = [
        {
            "xref": person.xref,
            "name": person.name,
            "sex": person.sex,
            "birth_date": person.birth_date,
            "death_date": person.death_date,
            "father_xref": person.father_xref,
            "mother_xref": person.mother_xref,
        }
        for person in parsed.people
    ]
    output = export_gedcom(version="7.0", people=payload)
    assert "0 HEAD" in output
    assert "2 VERS 7.0" in output
    assert "0 TRLR" in output
