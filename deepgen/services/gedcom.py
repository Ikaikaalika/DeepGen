import re
from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass
class ParsedPerson:
    xref: str
    name: str
    sex: str | None
    birth_date: str | None
    death_date: str | None
    birth_year: int | None
    is_living: bool
    father_xref: str | None
    mother_xref: str | None


@dataclass
class GedcomParseResult:
    version: str
    people: list[ParsedPerson]


def _extract_year(value: str | None) -> int | None:
    if not value:
        return None
    matches = re.findall(r"(\d{4})", value)
    if not matches:
        return None
    year = int(matches[-1])
    if 1500 <= year <= 2100:
        return year
    return None


def infer_living_status(birth_year: int | None, death_date: str | None) -> bool:
    if death_date:
        return False
    current_year = datetime.now(UTC).year
    if birth_year is None:
        # Conservative privacy default: unknown age is treated as possibly living.
        return True
    if birth_year <= current_year - 120:
        return False
    return True


def _parse_gedcom_line(line: str) -> tuple[int, str | None, str, str]:
    parts = line.strip().split(" ", 2)
    if len(parts) < 2:
        raise ValueError(f"Invalid GEDCOM line: {line!r}")
    level = int(parts[0])
    second = parts[1]
    if second.startswith("@") and len(parts) >= 3:
        remainder = parts[2].split(" ", 1)
        tag = remainder[0]
        value = remainder[1] if len(remainder) == 2 else ""
        return level, second, tag, value
    value = parts[2] if len(parts) == 3 else ""
    return level, None, second, value


def parse_gedcom_text(content: str) -> GedcomParseResult:
    individuals: dict[str, dict] = {}
    families: dict[str, dict] = {}
    version = "unknown"

    current_record_type: str | None = None
    current_xref: str | None = None
    current_event: str | None = None
    in_gedc_block = False

    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            level, pointer, tag, value = _parse_gedcom_line(line)
        except ValueError:
            continue

        if level == 0:
            current_event = None
            in_gedc_block = False
            current_record_type = tag if pointer else tag
            current_xref = pointer
            if current_record_type == "INDI" and current_xref:
                individuals.setdefault(
                    current_xref,
                    {
                        "name": "Unknown",
                        "sex": None,
                        "birth_date": None,
                        "death_date": None,
                        "famc": [],
                    },
                )
            if current_record_type == "FAM" and current_xref:
                families.setdefault(current_xref, {"husb": None, "wife": None, "chil": []})
            continue

        if current_record_type == "HEAD":
            if level == 1 and tag == "GEDC":
                in_gedc_block = True
            elif level == 1:
                in_gedc_block = False
            if in_gedc_block and level == 2 and tag == "VERS":
                version = value.strip() or version
            continue

        if current_record_type == "INDI" and current_xref:
            person = individuals[current_xref]
            if level == 1:
                current_event = None
                if tag == "NAME":
                    person["name"] = value.replace("/", "").strip() or "Unknown"
                elif tag == "SEX":
                    person["sex"] = value.strip() or None
                elif tag in {"BIRT", "DEAT"}:
                    current_event = tag
                elif tag == "FAMC":
                    fam_id = value.strip()
                    if fam_id:
                        person["famc"].append(fam_id)
            elif level == 2 and tag == "DATE" and current_event:
                if current_event == "BIRT":
                    person["birth_date"] = value.strip() or None
                if current_event == "DEAT":
                    person["death_date"] = value.strip() or None
            continue

        if current_record_type == "FAM" and current_xref:
            family = families[current_xref]
            if level == 1 and tag == "HUSB":
                family["husb"] = value.strip() or None
            if level == 1 and tag == "WIFE":
                family["wife"] = value.strip() or None
            if level == 1 and tag == "CHIL":
                child_xref = value.strip()
                if child_xref:
                    family["chil"].append(child_xref)

    people: list[ParsedPerson] = []
    for xref, data in individuals.items():
        father_xref = None
        mother_xref = None
        for family_id in data["famc"]:
            fam = families.get(family_id)
            if fam:
                father_xref = fam.get("husb")
                mother_xref = fam.get("wife")
                break
        birth_year = _extract_year(data["birth_date"])
        is_living = infer_living_status(birth_year, data["death_date"])
        people.append(
            ParsedPerson(
                xref=xref,
                name=data["name"],
                sex=data["sex"],
                birth_date=data["birth_date"],
                death_date=data["death_date"],
                birth_year=birth_year,
                is_living=is_living,
                father_xref=father_xref,
                mother_xref=mother_xref,
            )
        )
    people.sort(key=lambda p: p.xref)
    return GedcomParseResult(version=version, people=people)


def export_gedcom(version: str, people: list[dict]) -> str:
    lines: list[str] = []
    lines.append("0 HEAD")
    lines.append("1 SOUR DeepGen")
    lines.append("1 GEDC")
    lines.append(f"2 VERS {version}")
    lines.append("2 FORM LINEAGE-LINKED")
    lines.append("1 CHAR UTF-8")

    family_map: dict[tuple[str | None, str | None], str] = {}
    family_children: dict[str, list[str]] = {}
    family_index = 1

    for person in people:
        father = person.get("father_xref")
        mother = person.get("mother_xref")
        if not father and not mother:
            continue
        key = (father, mother)
        if key not in family_map:
            fam_xref = f"@F{family_index}@"
            family_index += 1
            family_map[key] = fam_xref
            family_children[fam_xref] = []
        family_children[family_map[key]].append(person["xref"])

    child_family_link: dict[str, str] = {}
    for fam_xref, children in family_children.items():
        for child in children:
            child_family_link[child] = fam_xref

    for person in people:
        lines.append(f"0 {person['xref']} INDI")
        lines.append(f"1 NAME {person.get('name') or 'Unknown'}")
        if person.get("sex"):
            lines.append(f"1 SEX {person['sex']}")
        if person.get("birth_date"):
            lines.append("1 BIRT")
            lines.append(f"2 DATE {person['birth_date']}")
        if person.get("death_date"):
            lines.append("1 DEAT")
            lines.append(f"2 DATE {person['death_date']}")
        famc = child_family_link.get(person["xref"])
        if famc:
            lines.append(f"1 FAMC {famc}")

    for (father, mother), fam_xref in family_map.items():
        lines.append(f"0 {fam_xref} FAM")
        if father:
            lines.append(f"1 HUSB {father}")
        if mother:
            lines.append(f"1 WIFE {mother}")
        for child in family_children[fam_xref]:
            lines.append(f"1 CHIL {child}")

    lines.append("0 TRLR")
    return "\n".join(lines) + "\n"
