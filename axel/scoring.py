import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import dotenv
import requests

dotenv.load_dotenv()

API_KEY = os.getenv("API_KEY")
API_USER = os.getenv("API_USER")
SOURCE_KEY_2 = os.getenv("SOURCE_KEY_2")
SOURCE_KEY = os.getenv("SOURCE_KEY")
JOB_KEY = os.getenv("JOB_KEY")
BOARD_KEY = os.getenv("BOARD_KEY")

def _scoring_url(page: int, limit: int, source_key: str) -> str:
    """URL du scoring HrFlow ; l'API est paginée (page, limit). `source_key` = source HrFlow."""
    return (
        f"https://api.hrflow.ai/v1/profiles/scoring?"
        f"algorithm_key=b1ebac4c62fa96e06206f4433b95ae69674891ff&use_algorithm=1&"
        f"job_key={JOB_KEY}&board_key={BOARD_KEY}&"
        f"source_keys=%5B%22{source_key}%22%5D&page={page}&limit={limit}&"
        f"order_by=desc&location_geopoint=&enrich_text_keywords=false"
    )


PAGE_LIMIT = 30

headers = {
    "accept": "application/json",
    "X-API-KEY": API_KEY,
    "X-USER-EMAIL": API_USER,
}


def load_candidates_profile_names(candidates_dir: str | os.PathLike[str]) -> dict[str, str]:
    """
    Charge reference (et nom de fichier .json) -> nom affiché depuis les JSON
    locaux (metadata.profile_name), pour compléter l'API quand info est vide.
    Indexe aussi les emails (minuscules) pour le rapprochement avec info.email.
    """
    out: dict[str, str] = {}
    root = Path(candidates_dir)
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        ref = data.get("reference")
        if ref is None or str(ref).strip() == "":
            ref = path.stem
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        name = (meta.get("profile_name") or "").strip()
        if not name:
            continue
        out[str(ref)] = name
        out[path.stem] = name
        hk = (data.get("hrflow_key") or meta.get("hrflow_key") or "").strip()
        if hk:
            out[hk] = name
        for em in data.get("emails") or []:
            if isinstance(em, str) and em.strip():
                out[em.strip().lower()] = name
    return out


def load_ordered_display_names(candidates_dir: str | os.PathLike[str]) -> list[str]:
    """
    Noms affichables dans l'ordre stable des fichiers (tri par nom de fichier),
    pour associer chaque ligne de scoring à un candidat quand l'API ne donne pas le nom.
    """
    out: list[str] = []
    root = Path(candidates_dir)
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}
        name = (meta.get("profile_name") or "").strip()
        if name:
            out.append(name)
    return out


def _is_placeholder_name(name: str) -> bool:
    return bool(re.match(r"^Profil #\d+$", name.strip()))


def _is_hrflow_hex_key(name: str) -> bool:
    s = name.strip()
    return len(s) >= 32 and re.fullmatch(r"[a-f0-9]+", s.lower()) is not None


def deep_find_profile_name(obj: Any, depth: int = 0) -> str:
    """Cherche une chaîne profile_name dans l'arbre JSON du profil HrFlow."""
    if depth > 12:
        return ""
    if isinstance(obj, dict):
        v = obj.get("profile_name")
        if isinstance(v, str) and v.strip():
            return v.strip()
        for x in obj.values():
            r = deep_find_profile_name(x, depth + 1)
            if r:
                return r
    elif isinstance(obj, list):
        for x in obj:
            r = deep_find_profile_name(x, depth + 1)
            if r:
                return r
    return ""


def prediction_score(pred: list | tuple) -> float:
    """Score utile : 2e valeur du couple (ex. [1-p, p] → p)."""
    if not isinstance(pred, (list, tuple)) or len(pred) < 2:
        raise ValueError(f"Prédiction attendue [_, score], reçu : {pred!r}")
    return float(pred[1])


def profile_display_name(
    profile: dict[str, Any],
    index: int,
    name_lookup: dict[str, str] | None = None,
) -> str:
    """
    Nom affiché d'un profil HrFlow (cf. developers.hrflow.ai — objet Profile / info).
    Puis noms issus des JSON locaux (référence / clé) si info est vide.
    """
    name_lookup = name_lookup or {}
    if not isinstance(profile, dict):
        return f"Profil #{index + 1}"
    info = profile.get("info")
    if isinstance(info, dict):
        full = (info.get("full_name") or "").strip()
        if full:
            return full
        fn = (info.get("first_name") or info.get("firstname") or "").strip()
        ln = (info.get("last_name") or info.get("lastname") or "").strip()
        if fn or ln:
            return f"{fn} {ln}".strip()
        name = (info.get("name") or "").strip()
        if name:
            return name
    ref = profile.get("reference")
    if ref is not None and str(ref) in name_lookup:
        return name_lookup[str(ref)]
    key = profile.get("key")
    if key is not None and str(key) in name_lookup:
        return name_lookup[str(key)]
    meta = profile.get("metadata")
    if isinstance(meta, dict):
        pn = (meta.get("profile_name") or "").strip()
        if pn:
            return pn
    if isinstance(info, dict):
        em = (info.get("email") or "").strip().lower()
        if em and em in name_lookup:
            return name_lookup[em]
    for em in profile.get("emails") or []:
        if isinstance(em, str):
            e = em.strip().lower()
            if e and e in name_lookup:
                return name_lookup[e]
    deep = deep_find_profile_name(profile)
    if deep:
        return deep
    return f"Profil #{index + 1}"


def unique_predictions_first_occurrence(
    predictions: list,
) -> list[tuple[list | tuple, int]]:
    """
    L'API peut renvoyer plusieurs fois la même paire [1-score, score]. On garde
    chaque tuple unique avec l'indice de sa **première** occurrence : c'est le
    même indice que data.profiles[i] (tableau parallèle à predictions).
    """
    seen: set[tuple[Any, ...]] = set()
    out: list[tuple[list | tuple, int]] = []
    for i, p in enumerate(predictions):
        t = tuple(p)
        if t not in seen:
            seen.add(t)
            out.append((p, i))
    return out


def build_ranking(
    predictions: list,
    profiles: list[dict[str, Any]] | None,
    name_lookup: dict[str, str] | None = None,
    fallback_ordered_names: list[str] | None = None,
) -> list[tuple[str, float, int]]:
    """
    Une entrée par prédiction distincte (dédupliquée). Si le nom reste « Profil #n »
    ou une clé hex illisible, on prend le i-ième nom de candidates_split (même ordre
    que les premières occurrences de scores dans la réponse).
    """
    pairs = unique_predictions_first_occurrence(predictions)
    if not profiles:
        profiles = []
    fallback_ordered_names = fallback_ordered_names or []
    scored: list[tuple[str, float, int]] = []
    for i, (pred, first_idx) in enumerate(pairs):
        if first_idx < len(profiles) and isinstance(profiles[first_idx], dict):
            name = profile_display_name(profiles[first_idx], first_idx, name_lookup)
        else:
            name = f"Profil #{first_idx + 1}"
        if i < len(fallback_ordered_names) and (
            _is_placeholder_name(name) or _is_hrflow_hex_key(name)
        ):
            name = fallback_ordered_names[i]
        scored.append((name, prediction_score(pred), first_idx))
    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


def score_to_percent(score: float) -> str:
    return f"{100.0 * score:.2f}%"


def ranking_table(rows: list[tuple[str, float]]) -> str:
    """Tableau texte : rang, nom, score en %."""
    if not rows:
        return "(aucun résultat)"
    w_rank = max(3, len(str(len(rows))))
    w_name = max(len(name) for name, _ in rows)
    w_pct = max(len(score_to_percent(s)) for _, s in rows)
    sep = f"+{'-' * (w_rank + 2)}+{'-' * (w_name + 2)}+{'-' * (w_pct + 2)}+"
    lines = [sep, f"| {'Rang':^{w_rank}} | {'Nom':^{w_name}} | {'Score':^{w_pct}} |", sep]
    for r, (name, score) in enumerate(rows, start=1):
        pct = score_to_percent(score)
        lines.append(f"| {r:^{w_rank}} | {name:<{w_name}} | {pct:>{w_pct}} |")
    lines.append(sep)
    return "\n".join(lines)


def ranking_from_payload(
    payload: dict[str, Any],
    name_lookup: dict[str, str] | None = None,
    fallback_ordered_names: list[str] | None = None,
) -> list[tuple[str, float, str, int]]:
    """
    Retourne une liste de tuples (nom, score_brut, score %, first_idx), triée par
    score décroissant. first_idx sert à retrouver le profil API pour l'export sans JSON local.
    """
    data = payload.get("data") or {}
    predictions = data.get("predictions")
    if not isinstance(predictions, list):
        raise ValueError("Réponse invalide : pas de liste 'predictions' dans data.")

    profiles = data.get("profiles")
    if profiles is not None and not isinstance(profiles, list):
        profiles = None

    ranked = build_ranking(
        predictions, profiles, name_lookup, fallback_ordered_names=fallback_ordered_names
    )
    return [
        (name, score, score_to_percent(score), first_idx)
        for name, score, first_idx in ranked
    ]


def fetch_merged_scoring_payload(source_key: str) -> dict[str, Any]:
    """
    Enchaîne les pages jusqu'à maxPage (meta) : une seule requête ne renvoie que
    PAGE_LIMIT lignes ; le total (ex. 119) est dans meta.total, pas dans une page.
    """
    page = 1
    all_predictions: list[Any] = []
    all_profiles: list[Any] = []
    last_payload: dict[str, Any] = {}
    first_meta: dict[str, Any] = {}
    total_expected: int | None = None
    while page <= 500:
        u = _scoring_url(page, PAGE_LIMIT, source_key)
        r = requests.get(u, headers=headers)
        payload = r.json()
        last_payload = payload
        if r.status_code != 200:
            return payload
        if payload.get("code") not in (None, 200):
            return payload
        data = payload.get("data") or {}
        preds = data.get("predictions")
        profs = data.get("profiles")
        if not isinstance(preds, list):
            break
        if not isinstance(profs, list):
            profs = []
        meta = payload.get("meta") or {}
        if page == 1:
            first_meta = dict(meta)
            t = meta.get("total")
            if t is not None:
                try:
                    total_expected = int(t)
                except (TypeError, ValueError):
                    total_expected = None
        all_predictions.extend(preds)
        all_profiles.extend(profs)
        max_page = meta.get("maxPage") or meta.get("max_page")
        count = meta.get("count")
        if not preds:
            break
        if total_expected is not None and len(all_predictions) >= total_expected:
            break
        if max_page is not None and page >= int(max_page):
            break
        if count is not None and int(count) < PAGE_LIMIT:
            break
        page += 1
    merged_meta = dict(first_meta or last_payload.get("meta") or {})
    merged_meta["fetched_prediction_rows"] = len(all_predictions)
    merged_meta["fetched_profile_rows"] = len(all_profiles)
    return {
        "code": last_payload.get("code"),
        "message": last_payload.get("message"),
        "meta": merged_meta,
        "data": {"predictions": all_predictions, "profiles": all_profiles},
    }


_SCRIPT_DIR = Path(__file__).resolve().parent
_DATA_DIR = _SCRIPT_DIR / "data"
OUTPUT_PATH = _DATA_DIR / "grading_output.json"
SUMMARY_PATH = _DATA_DIR / "grading_summary.txt"
TOP_N_PER_SOURCE = 5


def load_candidates_from_split(candidates_dir: Path) -> list[dict[str, Any]]:
    """Charge tous les candidats depuis candidates_split/*.json (liste d'objets)."""
    out: list[dict[str, Any]] = []
    if not candidates_dir.is_dir():
        return out
    for path in sorted(candidates_dir.glob("*.json")):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def resolve_candidate_name(candidate: dict) -> str:
    name = (candidate.get("name") or "").strip()
    if name and name.lower() != "unknown":
        return name
    
    meta = candidate.get("metadata") or {}
    if not isinstance(meta, dict):
        meta = {}
    meta_name = (meta.get("profile_name") or "").strip()
    if meta_name and meta_name.lower() != "unknown":
        return meta_name

    title = (candidate.get("title") or "").strip()
    if title and title.lower() != "unknown":
        for suffix in [" - GitHub", " | LinkedIn", " (GitHub)"]:
            if title.endswith(suffix):
                title = title[:-len(suffix)]
        return title

    url = (candidate.get("source_url") or "").strip()
    if url:
        path = urlparse(url).path.strip("/")
        if path:
            slug = path.split("/")[-1]
            if slug:
                return slug
    return "Candidat Inconnu"

def build_candidate_brief(candidate: dict) -> str:
    hint = (candidate.get("summary_hint") or "").strip()
    if not hint:
        text = candidate.get("text") or candidate.get("raw_text") or ""
        text = " ".join(text.split())
        hint = text[:137] + "..." if len(text) > 140 else text
    return hint if hint else "N/A"


def synthetic_candidate_from_hrflow_profile(
    profile: dict[str, Any],
    display_name: str,
    rank: int,
    raw_score: float,
    pct: str,
    origin_kind: str = "external",
    origin_description: str = "",
) -> dict[str, Any]:
    """Export au même format que les JSON locaux quand seul le profil API est disponible."""
    info = profile.get("info") if isinstance(profile.get("info"), dict) else {}
    summary = (info.get("summary") or "").strip()
    text = (profile.get("text") or "").strip()
    loc = ""
    lo = info.get("location")
    if isinstance(lo, str):
        loc = lo.strip()
    elif isinstance(lo, dict):
        loc = (lo.get("text") or "").strip()
    synth: dict[str, Any] = {
        "display_name": display_name,
        "summary_hint": summary,
        "text": text,
        "metadata": {"profile_name": display_name, "location": loc},
        "projects": profile.get("projects") or [],
        "rank": rank,
        "score": raw_score,
        "score_percent": pct,
        "source": "hrflow_api",
        "origin_kind": origin_kind,
        "origin_description": origin_description,
    }
    synth["brief"] = build_candidate_brief(synth)
    return synth


def extract_useful_candidate_facts(candidate: dict) -> dict:
    meta = candidate.get("metadata", {})
    if not isinstance(meta, dict):
        meta = {}
    brief = (candidate.get("brief") or "").strip()
    if brief == "N/A":
        brief = ""

    brief = brief.replace("\n", " ").replace("#", "").strip()
    if len(brief) > 120:
        brief = brief[:117] + "..."

    return {
        "name": candidate.get("display_name", "Candidat"),
        "location": meta.get("location", "").strip(),
        "brief": brief,
        "projects_count": len(candidate.get("projects", [])),
    }


def _norm_name(s: str) -> str:
    return s.strip().lower()


def match_candidate_for_ranking_row(
    ranking_name: str,
    candidates: list[dict[str, Any]],
    used_indices: set[int],
) -> int | None:
    """Retourne l'indice du candidat dont le nom affiché correspond au classement."""
    target = _norm_name(ranking_name)
    for i, cand in enumerate(candidates):
        if i in used_indices:
            continue
        if _norm_name(resolve_candidate_name(cand)) == target:
            return i
    for i, cand in enumerate(candidates):
        if i in used_indices:
            continue
        m = cand.get("metadata")
        if isinstance(m, dict):
            pn = (m.get("profile_name") or "").strip()
            if pn and _norm_name(pn) == target:
                return i
    return None


def build_top_candidates_for_source(
    ranking: list[tuple[str, float, str, int]],
    candidates: list[dict[str, Any]],
    profiles_api: list[dict[str, Any]],
    top_n: int,
    origin_kind: str,
    origin_description: str,
) -> list[dict[str, Any]]:
    """
    Top N du classement pour une source HrFlow : JSON local si match, sinon profil API.
    `origin_kind` distingue scraping externe vs postulants internes.
    """
    used: set[int] = set()
    out: list[dict[str, Any]] = []
    profs = profiles_api or []
    for rank, (name, raw_score, pct, first_idx) in enumerate(ranking[:top_n], start=1):
        idx = match_candidate_for_ranking_row(name, candidates, used)
        if idx is not None:
            used.add(idx)
            cand = dict(candidates[idx])
            cand["display_name"] = name
            cand["brief"] = build_candidate_brief(cand)
            cand["rank"] = rank
            cand["score"] = raw_score
            cand["score_percent"] = pct
            cand["source"] = "local_json"
            cand["origin_kind"] = origin_kind
            cand["origin_description"] = origin_description
            out.append(cand)
        elif first_idx < len(profs) and isinstance(profs[first_idx], dict):
            out.append(
                synthetic_candidate_from_hrflow_profile(
                    profs[first_idx],
                    name,
                    rank,
                    raw_score,
                    pct,
                    origin_kind=origin_kind,
                    origin_description=origin_description,
                )
            )
        else:
            out.append(
                {
                    "display_name": name,
                    "brief": "N/A",
                    "rank": rank,
                    "score": raw_score,
                    "score_percent": pct,
                    "source": "ranking_only",
                    "origin_kind": origin_kind,
                    "origin_description": origin_description,
                }
            )
    return out


def _paragraphs_for_candidate_summaries(selected_candidates: list) -> list[str]:
    """Phrases pour chaque candidat (ordre local au sein de la liste)."""
    descriptions: list[str] = []
    for i, cand in enumerate(selected_candidates):
        f = extract_useful_candidate_facts(cand)
        name = f["name"]
        loc = f["location"]
        brief = f["brief"]
        has_loc = loc and loc.lower() != "unknown"
        pct = (cand.get("score_percent") or "").strip()

        if i == 0:
            s = f"{name} ressort en tête"
            if pct:
                s += f" avec un score d'environ {pct}"
            s += " : c'est un profil"
            if has_loc:
                s += f" basé à {loc}"
            if brief:
                s += f", {brief}"
            if f["projects_count"] > 0:
                s += " avec plusieurs projets visibles"
            descriptions.append(s)
        elif i == 1:
            s = f"{name} apparaît aussi comme un profil intéressant"
            if pct:
                s += f" ({pct})"
            if has_loc:
                s += f", également basé à {loc}"
            if brief:
                s += f", avec un positionnement sur {brief}"
            descriptions.append(s)
        elif i == 2:
            s = f"{name} complète le podium"
            if pct:
                s += f" ({pct})"
            if brief:
                s += f" avec {brief}"
            descriptions.append(s)
        else:
            ordinals = {3: "quatrième", 4: "cinquième", 5: "sixième"}
            ord_ = ordinals.get(i, f"{i + 1}e")
            s = f"En {ord_} position, {name}"
            if pct:
                s += f" ({pct})"
            if brief:
                s += f" : {brief}"
            descriptions.append(s)

    paragraphs: list[str] = []
    for s in descriptions:
        s = s.strip()
        if s and not s.endswith((".", "!", "?")):
            s += "."
        if s:
            paragraphs.append(s)
    return paragraphs


def build_spoken_summary_two_sources(
    top_scraping: list[dict[str, Any]],
    top_applicants: list[dict[str, Any]],
    total_local_json: int,
    api_total_scraping: int | None,
    api_total_applicants: int | None,
) -> str:
    """Deux classements séparés : scraping externe (SOURCE_KEY) vs postulants (SOURCE_KEY_2)."""
    if not top_scraping and not top_applicants:
        return "Je n'ai trouvé aucun candidat à analyser (vérifiez les clés SOURCE_KEY / SOURCE_KEY_2 et le scoring)."


    pool_s = api_total_scraping if api_total_scraping is not None else "N/A"
    pool_a = api_total_applicants if api_total_applicants is not None else "N/A"

    sec1 = (
        "=== 1. Top 5 — Scraping externe (variable SOURCE_KEY) ===\n\n"
        "Ces profils sont indexés depuis la source associée au scraping externe "
        "(collecte hors parcours de candidature classique). "
        f"Volume côté API pour cette source : {pool_s} profil(s) au total (meta.total).\n\n"
    )
    if not top_scraping:
        sec1 += "Aucun résultat exploitable pour cette source (clé absente, liste vide, ou erreur API).\n\n"
    else:
        sec1 += "\n\n".join(_paragraphs_for_candidate_summaries(top_scraping)) + "\n\n"

    sec2 = (
        "=== 2. Top 5 — Candidats ayant postulé (variable SOURCE_KEY_2) ===\n\n"
        "Ces profils correspondent aux personnes qui ont déposé une candidature "
        "(flux interne / postulants). "
        f"Volume côté API pour cette source : {pool_a} profil(s) au total (meta.total).\n\n"
    )
    if not top_applicants:
        sec2 += "Aucun résultat exploitable pour cette source.\n\n"
    else:
        sec2 += "\n\n".join(_paragraphs_for_candidate_summaries(top_applicants)) + "\n\n"

    return sec1 + sec2


def _process_one_hrflow_source(
    source_key: str | None,
    label: str,
    origin_kind: str,
    origin_description: str,
    names_map: dict[str, str],
    ordered_names: list[str],
    candidates: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any], int | None]:
    """Récupère le scoring paginé, classe, retourne le top 5 et meta.total."""
    if not source_key or not str(source_key).strip():
        print(f"⚠️ {label} : clé de source absente dans .env, ignoré.")
        return [], {}, None
    print(f"\n{'=' * 60}\n{label}\nsource_key={source_key}\n{'=' * 60}")
    payload = fetch_merged_scoring_payload(source_key.strip())
    if payload.get("code") not in (None, 200):
        print(f"HrFlow code={payload.get('code')} message={payload.get('message')!r}")
        print(payload)
        return [], payload, None

    meta = payload.get("meta") or {}
    api_total_raw = meta.get("total")
    try:
        api_total = int(api_total_raw) if api_total_raw is not None else None
    except (TypeError, ValueError):
        api_total = None
    print(
        f"Meta : total={api_total!r}, lignes prédictions={meta.get('fetched_prediction_rows')}, "
        f"profils={meta.get('fetched_profile_rows')}"
    )

    predictions = (payload.get("data") or {}).get("predictions")
    if not isinstance(predictions, list) or not predictions:
        print("Aucune prédiction pour cette source.")
        return [], payload, api_total

    try:
        ranking = ranking_from_payload(
            payload,
            name_lookup=names_map,
            fallback_ordered_names=ordered_names,
        )
    except ValueError as e:
        print(e)
        return [], payload, api_total

    profiles_api = (payload.get("data") or {}).get("profiles")
    if not isinstance(profiles_api, list):
        profiles_api = []

    print(f"--- Classement ({label}, scores uniques) ---")
    for name, raw, pct, _ in ranking:
        print(f"{name}\t{pct} ({raw:.6f})")
    print()
    print(ranking_table([(n, s) for n, s, _, _ in ranking]))
    print()

    top = build_top_candidates_for_source(
        ranking,
        candidates,
        profiles_api,
        TOP_N_PER_SOURCE,
        origin_kind,
        origin_description,
    )
    print(f"Top {TOP_N_PER_SOURCE} exportés : {len(top)} entrée(s).")
    return top, payload, api_total


def main() -> None:
    print("Récupération du scoring pour SOURCE_KEY (scraping) et SOURCE_KEY_2 (postulants)...")

    cdir = _SCRIPT_DIR / "candidates_split"
    names_map = load_candidates_profile_names(cdir)
    ordered_names = load_ordered_display_names(cdir)
    candidates = load_candidates_from_split(cdir)
    total_local = len(candidates)
    print(f"Fichiers JSON locaux (candidates_split) : {total_local}.")

    desc_scraping = (
        "Source HrFlow SOURCE_KEY : profils issus du scraping externe (hors parcours candidature)."
    )
    desc_applicants = (
        "Source HrFlow SOURCE_KEY_2 : candidats ayant postulé (interne au processus de recrutement)."
    )

    top_scraping, _payload_s, api_total_s = _process_one_hrflow_source(
        SOURCE_KEY,
        "Scraping externe",
        "scraping_externe",
        desc_scraping,
        names_map,
        ordered_names,
        candidates,
    )
    top_applicants, _payload_a, api_total_a = _process_one_hrflow_source(
        SOURCE_KEY_2,
        "Postulants (candidatures)",
        "postulants_interne",
        desc_applicants,
        names_map,
        ordered_names,
        candidates,
    )

    grading_export: dict[str, Any] = {
        "source_keys": {
            "SOURCE_KEY_scraping_externe": SOURCE_KEY,
            "SOURCE_KEY_2_postulants": SOURCE_KEY_2,
        },
        "top_scraping_externe": top_scraping,
        "top_postulants_interne": top_applicants,
        "description": {
            "top_scraping_externe": desc_scraping,
            "top_postulants_interne": desc_applicants,
        },
    }

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(grading_export, f, indent=4, ensure_ascii=False)
    print(f"\nÉcrit : {OUTPUT_PATH}")

    spoken_text = build_spoken_summary_two_sources(
        top_scraping,
        top_applicants,
        total_local,
        api_total_scraping=api_total_s,
        api_total_applicants=api_total_a,
    )
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        f.write(spoken_text)
    print(f"Écrit : {SUMMARY_PATH}")


if __name__ == "__main__":
    main()
