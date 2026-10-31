"""Track filtering and AST expression evaluation engine."""

from __future__ import annotations

import ast
from typing import Any

from mixsmith.core.exceptions import FilterSyntaxError
from mixsmith.core.models import Track
from mixsmith.utils.logging import get_logger

logger = get_logger("mixsmith.filters")


def evaluate_filter_expression(track: Track, expression: str) -> bool:
    """
    Safely evaluates a Python boolean expression against a Track object using AST parsing.
    Supports variables:
      name, artist, artists, genre, primary_genre, genres, theme,
      decade, era, year, release_year, language, popularity, duration_ms,
      explicit, is_clean, is_explicit.
    """
    if not expression or not expression.strip():
        return True

    # Build evaluation context
    var_map: dict[str, Any] = {
        "name": track.name.lower(),
        "artist": (track.primary_artist or "").lower(),
        "artists": [a.lower() for a in track.artists],
        "primary_artist": (track.primary_artist or "").lower(),
        "genre": (track.primary_genre or "").lower(),
        "primary_genre": (track.primary_genre or "").lower(),
        "genres": [g.lower() for g in track.all_genres],
        "all_genres": [g.lower() for g in track.all_genres],
        "theme": (track.theme or "").lower(),
        "decade": (track.decade or "").lower(),
        "era": (track.era or "").lower(),
        "year": track.release_year or 0,
        "release_year": track.release_year or 0,
        "language": (track.language or "").lower(),
        "popularity": track.popularity,
        "duration_ms": track.duration_ms,
        "duration_min": track.duration_ms / 60000.0,
        "explicit": track.explicit,
        "is_explicit": track.is_explicit,
        "is_clean": track.is_clean,
        "clean": track.is_clean
    }

    try:
        parsed = ast.parse(expression.strip(), mode="eval")

        def eval_node(node: ast.AST) -> Any:
            if isinstance(node, ast.Expression):
                return eval_node(node.body)
            elif isinstance(node, ast.BoolOp):
                if isinstance(node.op, ast.And):
                    return all(eval_node(v) for v in node.values)
                elif isinstance(node.op, ast.Or):
                    return any(eval_node(v) for v in node.values)
            elif isinstance(node, ast.UnaryOp):
                if isinstance(node.op, ast.Not):
                    return not eval_node(node.operand)
            elif isinstance(node, ast.Compare):
                left = eval_node(node.left)
                for op, comparator in zip(node.ops, node.comparators):
                    right = eval_node(comparator)
                    if isinstance(op, ast.Eq) and not (left == right) or isinstance(op, ast.NotEq) and not (left != right) or isinstance(op, ast.Lt) and not (left < right) or isinstance(op, ast.LtE) and not (left <= right) or isinstance(op, ast.Gt) and not (left > right) or isinstance(op, ast.GtE) and not (left >= right) or isinstance(op, ast.In) and left not in right or isinstance(op, ast.NotIn) and not (left not in right):
                        return False
                return True
            elif isinstance(node, ast.Name):
                key = node.id.lower()
                if key in var_map:
                    return var_map[key]
                raise FilterSyntaxError(f"Unknown variable in filter expression: '{node.id}'")
            elif isinstance(node, ast.Constant):
                val = node.value
                return val.lower() if isinstance(val, str) else val
            elif isinstance(node, ast.List):
                return [eval_node(e) for e in node.elts]
            elif isinstance(node, ast.BinOp):
                left = eval_node(node.left)
                right = eval_node(node.right)
                if isinstance(node.op, ast.Add):
                    return left + right
                elif isinstance(node.op, ast.Sub):
                    return left - right
            elif isinstance(node, ast.Call):
                # Allow .contains(arg)
                if isinstance(node.func, ast.Attribute) and node.func.attr == "contains":
                    target = eval_node(node.func.value)
                    arg = eval_node(node.args[0])
                    return str(arg) in str(target)

            raise FilterSyntaxError(f"Unsupported syntax in expression: {ast.dump(node)}")

        return bool(eval_node(parsed))
    except FilterSyntaxError:
        raise
    except Exception as e:
        logger.debug(f"Filter evaluation error for track {track.name}: {e}")
        return False


def filter_tracks(
    tracks: list[Track],
    artist_filter: str | None = None,
    genre_filter: str | None = None,
    theme_filter: str | None = None,
    decade_filter: str | None = None,
    language_filter: str | None = None,
    clean_only: bool = False,
    explicit_only: bool = False,
    min_year: int | None = None,
    max_year: int | None = None,
    min_popularity: int | None = None,
    max_popularity: int | None = None,
    filter_expr: str | None = None
) -> list[Track]:
    """Filters track collection across multiple dimensions."""
    filtered = list(tracks)

    if artist_filter:
        targets = [a.strip().lower() for a in artist_filter.split(",") if a.strip()]
        filtered = [
            t for t in filtered
            if any(t.has_artist(target) for target in targets)
        ]

    if genre_filter:
        targets = [g.strip().lower() for g in genre_filter.split(",") if g.strip()]
        filtered = [
            t for t in filtered
            if any(
                tg in t.primary_genre.lower() or
                tg.replace("-", " ") in t.primary_genre.lower() or
                any(tg in g.lower() for g in t.all_genres)
                for tg in targets
            )
        ]

    if theme_filter:
        targets = [th.strip().lower() for th in theme_filter.split(",") if th.strip()]
        filtered = [
            t for t in filtered
            if any(th in t.theme.lower() or th.replace("-", " ") in t.theme.lower() for th in targets)
        ]

    if decade_filter:
        targets = [d.strip().lower() for d in decade_filter.split(",") if d.strip()]
        filtered = [
            t for t in filtered
            if any(td == t.decade.lower() or td in t.era.lower() for td in targets)
        ]

    if language_filter:
        targets = [lang.strip().lower() for lang in language_filter.split(",") if lang.strip()]
        filtered = [
            t for t in filtered
            if any(tl in t.language.lower() for tl in targets)
        ]

    if clean_only:
        filtered = [t for t in filtered if t.is_clean]
    elif explicit_only:
        filtered = [t for t in filtered if t.is_explicit]

    if min_year is not None:
        filtered = [t for t in filtered if t.release_year and t.release_year >= min_year]
    if max_year is not None:
        filtered = [t for t in filtered if t.release_year and t.release_year <= max_year]

    if min_popularity is not None:
        filtered = [t for t in filtered if t.popularity is not None and t.popularity >= min_popularity]
    if max_popularity is not None:
        filtered = [t for t in filtered if t.popularity is not None and t.popularity <= max_popularity]

    if filter_expr:
        filtered = [t for t in filtered if evaluate_filter_expression(t, filter_expr)]

    return filtered
