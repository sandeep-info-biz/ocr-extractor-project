#!/usr/bin/env python3
import argparse
import json
import random
import subprocess
import tempfile
from pathlib import Path


def load_env_file(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or not line.startswith("export "):
            continue
        body = line[len("export ") :]
        if "=" not in body:
            continue
        k, v = body.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def run_curl_json(args: list[str]) -> dict:
    result = subprocess.run(args, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "curl failed")
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON response: {result.stdout[:300]}") from exc


def as_full_schema(row: dict, raw_text: str) -> dict:
    return {
        "first_name": row.get("first_name", ""),
        "last_name": row.get("last_name", ""),
        "phone_number": row.get("phone_number", ""),
        "email": row.get("email", ""),
        "date_of_birth": row.get("date_of_birth", ""),
        "gender": row.get("gender", ""),
        "religion": row.get("religion", ""),
        "marital_status": row.get("marital_status", ""),
        "nationality_country_name": row.get("nationality_country_name", ""),
        "country_region": row.get("country_region", ""),
        "city": row.get("city", ""),
        "postal_code": row.get("postal_code", ""),
        "languages": row.get("languages", []),
        "industry_type": row.get("industry_type", ""),
        "designation_or_position": row.get("designation_or_position", ""),
        "total_experience": row.get("total_experience", 0),
        "gulf_expierence": row.get("gulf_expierence", False),
        "passport_number": row.get("passport_number", ""),
        "passport_expiry_date": row.get("passport_expiry_date", ""),
        "skills": row.get("skills", []),
        "education": row.get("education", []),
        "education_degree": row.get("education_degree", ""),
        "about_description_summary": row.get("about_description_summary", ""),
        "linkedin_url": row.get("linkedin_url", ""),
        "raw_text": raw_text,
    }


def make_resume_text(row: dict, variant: int) -> str:
    education = row["education"][0]
    templates = [
        (
            "Name: {first} {last}\n"
            "Email: {email}\nPhone: {phone}\nDOB: {dob}\nGender: {gender}\n"
            "Location: {city}, {region}, {country} - {postal}\n"
            "Role: {role}\nExperience: {exp} years\nIndustry: {industry}\n"
            "Skills: {skills}\nLanguages: {langs}\n"
            "Education: {degree} in {field}, {institution} ({grad})\n"
            "LinkedIn: {linkedin}\nSummary: {summary}\n"
        ),
        (
            "{first} {last} | {role}\n"
            "{email} | {phone}\n"
            "Nationality: {country}\nMarital Status: {marital}\n"
            "Date of Birth - {dob}\nPassport: {passport} Exp: {passport_exp}\n"
            "Core Skills -> {skills}\nSpoken Languages -> {langs}\n"
            "Academic Background -> {degree}, {institution}, {grad}\n"
            "Profile: {summary}\n{linkedin}\n"
        ),
        (
            "RESUME\n"
            "Candidate: {first} {last}\n"
            "Contact: {email} / {phone}\n"
            "City: {city}\nCountry Region: {region}\n"
            "Total Experience: {exp}\n"
            "Designation or Position: {role}\n"
            "Industry Type: {industry}\n"
            "Languages Known: {langs}\n"
            "Technical Stack: {skills}\n"
            "Highest Degree: {degree}\n"
            "Field of Study: {field}\nInstitution: {institution}\n"
            "Graduation Year: {grad}\n"
            "About: {summary}\n"
            "Linkedin URL: {linkedin}\n"
        ),
    ]
    template = templates[variant % len(templates)]
    return template.format(
        first=row["first_name"],
        last=row["last_name"],
        email=row["email"],
        phone=row["phone_number"],
        dob=row["date_of_birth"],
        gender=row["gender"],
        city=row["city"],
        region=row["country_region"],
        country=row["nationality_country_name"],
        postal=row["postal_code"],
        role=row["designation_or_position"],
        exp=row["total_experience"],
        industry=row["industry_type"],
        skills=", ".join(row["skills"]),
        langs=", ".join(row["languages"]),
        degree=education["degree"],
        field=education["field_of_study"],
        institution=education["institution"],
        grad=education["graduation_year"],
        linkedin=row["linkedin_url"],
        summary=row["about_description_summary"],
        marital=row["marital_status"],
        passport=row["passport_number"] or "N/A",
        passport_exp=row["passport_expiry_date"] or "N/A",
    )


def build_rows(count: int) -> list[dict]:
    random.seed(42)
    first_names = [
        "Aarav", "Vihaan", "Reyansh", "Sai", "Arjun", "Aditya", "Kabir", "Ishaan", "Rohan", "Neel",
        "Ananya", "Ira", "Saanvi", "Myra", "Kiara", "Aditi", "Diya", "Meera", "Riya", "Nisha",
    ]
    last_names = [
        "Sharma", "Patel", "Reddy", "Nair", "Kumar", "Singh", "Gupta", "Das", "Iyer", "Mehta",
        "Verma", "Joshi", "Kapoor", "Mishra", "Yadav", "Chopra", "Bhat", "Pillai", "Rana", "Saxena",
    ]
    cities = ["Pune", "Bengaluru", "Hyderabad", "Mumbai", "Chennai", "Kochi", "Jaipur", "Noida", "Ahmedabad", "Delhi"]
    regions = ["Maharashtra", "Karnataka", "Telangana", "Tamil Nadu", "Kerala", "Rajasthan", "Uttar Pradesh", "Gujarat", "Delhi NCR", "West Bengal"]
    roles = ["Backend Developer", "Data Analyst", "QA Engineer", "DevOps Engineer", "Full Stack Developer"]
    industries = ["Information Technology", "Software Services", "FinTech", "E-Commerce", "Healthcare IT"]
    skill_banks = [
        ["Python", "FastAPI", "SQL"],
        ["Java", "Spring Boot", "PostgreSQL"],
        ["JavaScript", "React", "Node.js"],
        ["Docker", "Kubernetes", "AWS"],
        ["Pandas", "NumPy", "Machine Learning"],
    ]
    languages = [["English", "Hindi"], ["English", "Tamil"], ["English", "Telugu"], ["English", "Kannada"], ["English", "Malayalam"]]
    degrees = [("B.Tech", "Computer Science"), ("B.E.", "Information Technology"), ("MCA", "Computer Applications")]

    rows = []
    for i in range(count):
        first = first_names[i % len(first_names)]
        last = last_names[(i * 3) % len(last_names)]
        city = cities[i % len(cities)]
        region = regions[(i * 2) % len(regions)]
        role = roles[i % len(roles)]
        industry = industries[(i * 2) % len(industries)]
        skills = skill_banks[(i * 3) % len(skill_banks)]
        langs = languages[i % len(languages)]
        degree, field = degrees[i % len(degrees)]
        grad_year = 2015 + (i % 9)
        exp = 1 + (i % 9)
        phone = f"9{random.randint(100000000, 999999999)}"
        email = f"{first.lower()}.{last.lower()}{i+1}@example.com"
        dob = f"{1990 + (i % 10):04d}-{(i % 12) + 1:02d}-{(i % 28) + 1:02d}"

        rows.append(
            {
                "first_name": first,
                "last_name": last,
                "phone_number": phone,
                "email": email,
                "date_of_birth": dob,
                "gender": "Male" if i % 2 == 0 else "Female",
                "religion": "",
                "marital_status": "Single" if i % 3 else "Married",
                "nationality_country_name": "India",
                "country_region": region,
                "city": city,
                "postal_code": f"{400000 + (i * 13) % 99999}",
                "languages": langs,
                "industry_type": industry,
                "designation_or_position": role,
                "total_experience": exp,
                "gulf_expierence": bool(i % 5 == 0),
                "passport_number": f"P{random.randint(1000000, 9999999)}" if i % 4 == 0 else "",
                "passport_expiry_date": f"{2030 + (i % 5):04d}-12-31" if i % 4 == 0 else "",
                "skills": skills,
                "education": [
                    {
                        "degree": degree,
                        "field_of_study": field,
                        "institution": f"Institute {((i % 7) + 1)}",
                        "graduation_year": grad_year,
                    }
                ],
                "education_degree": degree,
                "about_description_summary": f"{role} with {exp} years of experience in {industry}.",
                "linkedin_url": f"https://linkedin.com/in/{first.lower()}{last.lower()}{i+1}",
            }
        )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description="Train mapping model through /extract + /feedback for synthetic resumes.")
    parser.add_argument("--count", type=int, default=20, help="Number of synthetic resumes to feed.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Python API base URL.")
    parser.add_argument("--mode", default="fast", choices=["fast", "balanced", "resume_bert"], help="Extraction mode.")
    args = parser.parse_args()

    env_map = load_env_file(Path(".run/dev.env"))
    token = env_map.get("SIMPLYPARSE_API_TOKEN", "").strip()
    if not token:
        raise SystemExit("Missing SIMPLYPARSE_API_TOKEN in .run/dev.env. Start app once to bootstrap env.")
    auth_header = f"Token {token}"

    rows = build_rows(args.count)
    success = 0
    failures = []

    for i, row in enumerate(rows, start=1):
        raw_text = make_resume_text(row, variant=i)
        corrected = as_full_schema(row, raw_text)

        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as fh:
            fh.write(raw_text)
            tmp_file = fh.name

        try:
            extract_resp = run_curl_json(
                [
                    "curl",
                    "-sS",
                    "-X",
                    "POST",
                    f"{args.base_url}/api/v1/extract",
                    "-H",
                    f"Authorization: {auth_header}",
                    "-F",
                    f"resume_file=@{tmp_file};type=text/plain",
                    "-F",
                    "preprocess=false",
                    "-F",
                    f"mode={args.mode}",
                    "-F",
                    "pdf_dpi=180",
                ]
            )
            token_id = str(extract_resp.get("token_id", "")).strip()
            if not token_id:
                raise RuntimeError(f"Missing token_id in extract response: {extract_resp}")

            feedback_payload = {
                "token_id": token_id,
                "rating": 5,
                "corrected_data": corrected,
                "retrain_on_submit": True,
            }
            feedback_resp = run_curl_json(
                [
                    "curl",
                    "-sS",
                    "-X",
                    "POST",
                    f"{args.base_url}/api/v1/feedback",
                    "-H",
                    f"Authorization: {auth_header}",
                    "-H",
                    "Content-Type: application/json",
                    "-d",
                    json.dumps(feedback_payload),
                ]
            )
            success += 1
            print(f"[{i:02d}/{args.count}] ok token={token_id} dataset={feedback_resp.get('total_dataset_entries')}")
        except Exception as exc:
            failures.append((i, str(exc)))
            print(f"[{i:02d}/{args.count}] failed: {exc}")
        finally:
            Path(tmp_file).unlink(missing_ok=True)

    print("\nSummary")
    print(f"  Success: {success}/{args.count}")
    print(f"  Failed : {len(failures)}")
    if failures:
        for idx, msg in failures[:5]:
            print(f"  - item {idx}: {msg}")


if __name__ == "__main__":
    main()
