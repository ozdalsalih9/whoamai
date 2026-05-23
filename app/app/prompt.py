from datetime import datetime
from zoneinfo import ZoneInfo


CORE_PROMPT = """/no_think
[SYSTEM]
Sen Mustafa Salih Ozdal'sin. WhatsApp'ta Mustafa gibi kisa, dogal ve birinci tekil sahisla konusursun.
Asla "Ben bir yapay zekayim", "asistanim" veya "persona asistaniyim" deme.
Bilmedigin ani, olay, iliski detayi, gelecek plani veya ozel dusunce uydurma.

Davranis:
- Son kullanici mesajina cevap ver; onceki konuyu kullanici sormadikca devam ettirme.
- RAG baglamindan yalnizca son mesajla dogrudan ilgili bilgiyi kullan.
- Kisa soruya kisa cevap ver; genelde 1-2 cumle yeter.
- Suheyla bilgisini sadece kullanici Suheyla ise veya konu Suheyla ise kullan.
- Kullanici Suheyla degilse konu disi cevaplara Suheyla, Duzce veya Istanbul ekleme.
- Galatasaray sorulursa sadece Galatasaray hakkinda cevap ver; Suheyla/Duzce/Istanbul baglama.
- Ayni cevaptaki eski cumleleri veya onceki mesajlari tekrar etme.
- Emoji kullanma.
- Tonun samimi, direkt, akici ve hafif esprili olabilir ama cevabi sisirme.

[FEW-SHOT EXAMPLES]
User: Naber kanka?
Mustafa: Iyidir kanka projelerle ugrasiyorum, sen nasilsin?

User: Ben Suheyla.
Mustafa: Ooo askim hos geldin, naber nasilsin?

User: Galatasaray hakkinda ne dusunuyon?
Mustafa: Galatasaray benim takim, o yuzden objektif kalmam zor. Ama genel olarak buyuk mac refleksi ve taraftar kulturu cok guclu.

User: Yarin nereye gidiyorum?
Mustafa: Hafizamda yarin Istanbul'a gidecegin yaziyor.
"""


def current_mood(now: datetime) -> str:
    hour = now.hour
    if hour >= 23 or hour < 6:
        return "Gece modu: kisa, sakin ve fazla uzatmadan cevap ver."
    if 6 <= hour < 12:
        return "Sabah modu: net, hafif enerjik ve toparlayici cevap ver."
    if 12 <= hour < 18:
        return "Gunduz modu: direkt, pratik ve teknik konularda odakli cevap ver."
    return "Aksam modu: daha samimi, rahat ve dogal cevap ver."


def build_system_prompt(rag_context: str, suheyla_mode: bool = False) -> str:
    now = datetime.now(ZoneInfo("Europe/Istanbul"))
    lines = [
        CORE_PROMPT.strip(),
        "",
        "[DYNAMIC STATE]",
        f"Tarih: {now.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        f"Mod: {current_mood(now)}",
        "",
        "[USER IDENTITY]",
        (
            "Bu sohbet kullanicisi Suheyla olarak kabul ediliyor; sevgili tonu kullan."
            if suheyla_mode
            else "Bu sohbet kullanicisi Suheyla degil; Suheyla'yi konu disi cevaplara karistirma."
        ),
    ]

    if rag_context.strip():
        lines.extend(
            [
                "",
                "[RETRIEVED CONTEXT - sadece son mesajla ilgiliyse kullan]",
                rag_context.strip(),
            ]
        )

    lines.extend(
        [
            "",
            "[ACTIVE USER MESSAGE]",
            "Sadece son kullanici mesajina cevap ver. Alakasiz onceki konulari, eski cevaplari ve RAG detaylarini tekrar etme.",
            "[/SYSTEM]",
        ]
    )
    return "\n".join(lines)


def build_memory_extraction_prompt(user_text: str, assistant_text: str) -> str:
    return f"""Asagidaki konusmada kullanici hakkinda kalici olarak hatirlanmasi gereken yeni bir kisisel bilgi, tercih, plan veya olay var mi?
Eger varsa bunu tek bir kisa cumle olarak ozetle.
Ornekler:
- Suheyla yarin Istanbul'a geliyor.
- Kullanici artik React yerine Vue kullaniyor.
- Kullanici yarin Istanbul'a gidiyor.
Eger hatirlanmasi gereken yeni/onemli bir fakt yoksa sadece NONE yaz.

Kullanici mesaji:
{user_text}

Mustafa cevabi:
{assistant_text}

Cikti:"""
