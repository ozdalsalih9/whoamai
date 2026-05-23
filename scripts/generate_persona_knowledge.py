#!/usr/bin/env python3
import argparse
import csv
from collections import defaultdict
from datetime import date
from pathlib import Path


CATEGORY_TITLES = {
    "identity": "Kimlik ve genel profil",
    "personality": "Kisilik ve iletisim tarzi",
    "habits": "Aliskanliklar",
    "interests": "Ilgi alanlari",
    "skills": "Beceriler",
    "preferences": "Tercihler",
    "sports": "Spor",
    "future_goals": "Gelecek hedefleri",
    "workspace": "Calisma ortami",
    "routines": "Rutinler",
    "interaction": "Etkilesim tarzi",
    "resources": "Kaynaklar",
    "active_context": "Aktif baglam",
}

FEATURE_LABELS = {
    "full_name": "Tam ad",
    "preferred_short_name": "Tercih edilen kisa ad",
    "age": "Yas",
    "gender": "Cinsiyet",
    "city": "Sehir",
    "hometown": "Memleket/bolge",
    "nationality": "Uyruk",
    "languages": "Diller",
    "education": "Egitim",
    "university": "Universite",
    "height_cm": "Boy",
    "weight_kg": "Kilo",
    "eye_color": "Goz rengi",
    "skin_tone": "Ten rengi",
    "humor_level": "Mizah seviyesi",
    "communication_style": "Iletisim tarzi",
    "truthfulness_importance": "Dogru soyleme hassasiyeti",
    "religious_orientation": "Dini yonelim",
    "stress_about_future": "Gelecek stresi",
    "decision_style": "Karar verme tarzi",
    "social_behavior": "Sosyal davranis",
    "language_style": "Dil tarzi",
    "swearing_frequency": "Kufur/argo sikligi",
    "respect_style": "Hitap tarzi",
    "learning_mindset": "Ogrenme yaklasimi",
    "curiosity_level": "Merak seviyesi",
    "startup_interest": "Girisim ilgisi",
    "security_awareness": "Guvenlik farkindaligi",
    "engineering_identity": "Muhendislik kimligi",
    "error_handling_style": "Hata cozme tarzi",
    "brainstorming_style": "Beyin firtinasi tarzi",
    "academic_tone": "Akademik ton",
    "smoking": "Sigara kullanimi",
    "alcohol": "Alkol kullanimi",
    "fitness_interest": "Fitness ilgisi",
    "sports_following": "Takip ettigi sporlar",
    "work_style": "Calisma tarzi",
    "research_behavior": "Arastirma davranisi",
    "software_backend": "Backend ilgisi",
    "frontend": "Frontend ilgisi",
    "ai_systems": "AI sistemleri ilgisi",
    "cybersecurity": "Siber guvenlik ilgisi",
    "automation": "Otomasyon ilgisi",
    "machine_learning": "Makine ogrenmesi ilgisi",
    "autonomous_systems": "Otonom sistemler ilgisi",
    "server_systems": "Sunucu sistemleri ilgisi",
    "networking": "Ag ilgisi",
    "database_systems": "Veritabani sistemleri ilgisi",
    "ecommerce_systems": "E-ticaret sistemleri ilgisi",
    "agentic_ai": "Ajan tabanli AI ilgisi",
    "local_llm": "Local LLM ilgisi",
    "vector_databases": "Vektor veritabani ilgisi",
    "rag_systems": "RAG sistemleri ilgisi",
    "aspnet_core": "ASP.NET Core seviyesi",
    "react": "React seviyesi",
    "sql": "SQL seviyesi",
    "system_design": "Sistem tasarimi seviyesi",
    "linux_server_management": "Linux sunucu yonetimi seviyesi",
    "prompt_engineering": "Prompt engineering seviyesi",
    "ai_architecture": "AI mimarisi seviyesi",
    "problem_solving": "Problem cozme seviyesi",
    "english_level": "Ingilizce seviyesi",
    "ui_theme": "Arayuz tema tercihi",
    "response_style": "Cevap tarzi tercihi",
    "technical_terms_language": "Teknik terim dili",
    "architecture_preference": "Mimari tercihi",
    "development_style": "Gelistirme tarzi",
    "ai_assistant_goal": "AI asistan hedefi",
    "football_team": "Tuttugu futbol takimi",
    "nba_player_followed": "Takip ettigi NBA oyuncusu",
    "build_ai_products": "AI urunleri gelistirme hedefi",
    "entrepreneurship_interest": "Girisimcilik ilgisi",
    "technical_mastery": "Teknik ustalik hedefi",
    "personal_ai_assistant": "Kisisel AI asistan hedefi",
    "primary_os": "Birincil isletim sistemleri",
    "primary_ide": "Birincil IDE/editor",
    "vps_os": "VPS isletim sistemi",
    "peak_productivity_hours": "En verimli saatler",
    "budget_preference": "Butce/araç tercihi",
    "current_main_project": "Guncel ana proje",
    "graduation_project": "Mezuniyet projesi",
    "other_active_projects": "Diger aktif projeler",
}

VALUE_TRANSLATIONS = {
    "male": "erkek",
    "Turkish": "Turkce",
    "English(B2)": "Ingilizce (B2)",
    "Istanbul": "Istanbul",
    "Uskudar Istanbul": "Üsküdar, İstanbul",
    "Bachelor Computer Engineering": "Bilgisayar Muhendisligi lisans ogrencisi/mezunu baglami",
    "Duzce University": "Düzce Üniversitesi",
    "green": "yesil",
    "light": "acik tenli",
    "high": "yuksek",
    "moderate": "orta",
    "technical_direct_friendly": "teknik, direkt ve arkadasca",
    "moderately_religious_muslim": "orta duzeyde dindar Musluman",
    "sometimes_impulsive": "bazen dusunmeden hizli karar verebilen",
    "loyal_social_group_oriented": "sadik ve sosyal grubuna onem veren",
    "casual_with_technical_depth": "rahat ama teknik derinligi olan",
    "occasional_light_swearing": "ara sira hafif argo kullanabilen",
    "uses_names_or_slang_like_kanka_reis": "kanka/reis gibi samimi hitaplar kullanabilen",
    "continuous_self_improvement": "surekli kendini gelistirmeye odakli",
    "strong": "guclu",
    "explain_first_then_fix": "once aciklayip sonra cozum onerme",
    "socratic_questioning": "sokratik sorularla fikir gelistirme",
    "professional_terminology": "profesyonel terminoloji",
    "no": "hayir",
    "football_and_basketball": "futbol ve basketbol",
    "project_oriented": "proje odakli",
    "deep_dives_into_topics": "konulara derinlemesine arastirmayla yaklasma",
    "medium_high": "orta-yuksek",
    "medium": "orta",
    "advanced_intermediate": "ileri-orta",
    "intermediate": "orta",
    "developing": "gelisim asamasinda",
    "beginner_intermediate": "baslangic-orta",
    "modern_dark_purple": "modern koyu mor tema",
    "concise_but_detailed": "kisa ama yeterince detayli",
    "english_preferred": "Ingilizce teknik terimler tercih edilir",
    "clean_scalable_secure": "temiz, olceklenebilir ve guvenli mimari",
    "iterative_building": "iteratif gelistirme",
    "personal_second_brain_ai": "kisisel ikinci beyin AI",
    "high_probability": "yuksek olasilik",
    "active_goal": "aktif hedef",
    "Personal_Second_Brain_AI_on_VPS": "VPS uzerinde kisisel ikinci beyin AI",
    "ML_DL_with_DOTNET_React": ".NET ve React ile ML/DL projesi",
    "WorldDeciding / Score Prediction": "WorldDeciding / skor tahmin projeleri",
    "Night time": "gece saatleri",
}


def humanize_feature(feature: str) -> str:
    return FEATURE_LABELS.get(feature, feature.replace("_", " "))


def humanize_value(value: str) -> str:
    parts = [part.strip() for part in value.split(";")]
    translated = [VALUE_TRANSLATIONS.get(part, part.replace("_", " ")) for part in parts if part]
    return "; ".join(translated)


def confidence_note(raw_confidence: str) -> tuple[float, str]:
    try:
        confidence = float(raw_confidence)
    except (TypeError, ValueError):
        confidence = 0.0

    if confidence >= 0.9:
        return confidence, "guven: yuksek"
    if confidence >= 0.8:
        return confidence, "guven: orta"
    return confidence, "guven: dusuk, kesin bilgi gibi sunma"


def read_rows(csv_path: Path) -> list[dict[str, str]]:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {"category", "feature", "value", "confidence", "notes"}
        missing = required.difference(reader.fieldnames or [])
        if missing:
            raise ValueError(f"CSV missing columns: {', '.join(sorted(missing))}")
        return list(reader)


def build_markdown(rows: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in rows:
        grouped[row["category"].strip()].append(row)

    lines = [
        "# Mustafa Persona Knowledge",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "Bu dokuman Mustafa Salih Ozdal persona chat sistemi icin bilgi tabanidir.",
        "Asistan bu bilgileri kesin kimlik dogrulamasi gibi degil, temkinli persona baglami olarak kullanmalidir.",
        "",
        "## Cevaplama kurallari",
        "",
        "- Mustafa'nin birebir kendisi oldugunu iddia etme.",
        "- Bilmedigin ani, olay, dusunce veya iliski detaylarini uydurma.",
        "- Dusuk guvenli bilgileri kesin ifade etme.",
        "- Turkce oncelikli, teknik, direkt, samimi ve temkinli cevap ver.",
        "- Kisisel veri ve hassas detaylarda minimum bilgi paylas.",
        "",
    ]

    for category, category_rows in grouped.items():
        title = CATEGORY_TITLES.get(category, category.replace("_", " ").title())
        lines.extend([f"## {title}", ""])
        for row in category_rows:
            feature = humanize_feature(row["feature"].strip())
            value = humanize_value(row["value"].strip())
            confidence, note = confidence_note(row["confidence"].strip())
            source_note = row["notes"].strip()
            low_conf_prefix = "Muhtemel bilgi: " if confidence < 0.8 else ""
            lines.append(f"- {low_conf_prefix}{feature}: {value}. ({note}; not: {source_note})")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Mustafa persona Knowledge Markdown from CSV.")
    parser.add_argument("--csv", required=True, type=Path, help="Input CSV path.")
    parser.add_argument("--out", default=Path("knowledge/mustafa_persona.md"), type=Path, help="Output Markdown path.")
    args = parser.parse_args()

    rows = read_rows(args.csv)
    markdown = build_markdown(rows)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(markdown, encoding="utf-8")
    print(f"Wrote {args.out} from {len(rows)} rows.")


if __name__ == "__main__":
    main()
