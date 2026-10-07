"""Deterministic pastel badges, shared by every category and anonymous visitors."""
import re

DEFAULT_REFERENCE = '#72828a'


def validate_color(value):
    """Accept only an opaque six-digit colour; never interpolate arbitrary CSS."""
    if not isinstance(value, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', value):
        raise ValueError('Choisissez une couleur valide.')
    return value.lower()


def normalize_color(value):
    try:
        return validate_color(value)
    except ValueError:
        return DEFAULT_REFERENCE


def _mix(color, target, reference_percent):
    # Integer rounding is identical on all platforms; no browser colour mixing.
    channels = [int(color[i:i + 2], 16) for i in (1, 3, 5)]
    return '#' + ''.join(f'{(v * reference_percent + target * (100 - reference_percent) + 50) // 100:02x}' for v in channels)


def luminance(color):
    values = [int(color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in values]
    return sum(v * w for v, w in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    dark, light = sorted((luminance(first), luminance(second)))
    return (light + 0.05) / (dark + 0.05)


def pastel_palette(value):
    reference = normalize_color(value)
    background = _mix(reference, 255, 10)
    ink = _mix(reference, 0, 40)
    # Final guard remains valid if the mixing ratios are changed in future.
    while contrast(background, ink) < 4.5:
        ink = _mix(ink, 0, 90)
    return {'reference': reference, 'background': background, 'ink': ink,
            'border': _mix(reference, 255, 15)}
