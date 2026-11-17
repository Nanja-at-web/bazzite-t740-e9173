"""Bounded synthetic JSON projection. No live KScreen version is verified.

SYNTHETIC_V1 explicitly defines size as the logical rectangle size. This fixture
format is not a D-Bus decoder and grants no compatibility or live permission.
"""
import json
import re
from math import isfinite
from .collect import CONNECTOR
from .host_reader import KScreenProfile, KOutput, KScreenData, ParseResult


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _number(value, low, high):
    return ((type(value) is int or type(value) is float)
            and low <= value <= high and isfinite(value))


def _pairs(pairs):
    if len(pairs) > 64:
        raise ValueError
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError
        result[key] = value
    return result


def _int_token(value):
    if len(value) > 12:
        raise ValueError
    result = int(value)
    if not -2147483648 <= result <= 2147483647:
        raise ValueError
    return result


def _preflight_json(text):
    """Validate bounded syntax/cardinality without allocating any containers."""
    nodes = 0
    length = len(text)

    def whitespace(index):
        while index < length and text[index] in ' \t\r\n':
            index += 1
        return index

    def string(index):
        end, escaped = index + 1, False
        while end < length:
            if end - index > 768:
                raise ValueError
            char = text[end]
            if not escaped and char == '"':
                value, after = json.decoder.scanstring(text, index + 1)
                if len(value) > 128 or len(value.encode('utf-8')) > 128:
                    raise ValueError
                return value, after
            if not escaped and char == '\\':
                escaped = True
            else:
                escaped = False
            end += 1
        raise ValueError

    def value(index, depth, parent=''):
        nonlocal nodes
        nodes += 1
        if depth > 8 or nodes > 8192:
            raise ValueError
        index = whitespace(index)
        if index >= length:
            raise ValueError
        char = text[index]
        if char == '"':
            return string(index)[1]
        if char == '{':
            index = whitespace(index + 1)
            keys = set()
            if index < length and text[index] == '}':
                return index + 1
            while index < length:
                if text[index] != '"' or len(keys) >= 64:
                    raise ValueError
                key, index = string(index)
                if key in keys:
                    raise ValueError
                keys.add(key)
                index = whitespace(index)
                if index >= length or text[index] != ':':
                    raise ValueError
                index = whitespace(value(index + 1, depth + 1, key))
                if index < length and text[index] == '}':
                    return index + 1
                if index >= length or text[index] != ',':
                    raise ValueError
                index = whitespace(index + 1)
            raise ValueError
        if char == '[':
            index = whitespace(index + 1)
            count = 0
            limit = 16 if parent in ('outputs', 'clones') else 128
            if index < length and text[index] == ']':
                return index + 1
            while index < length:
                if count >= limit:
                    raise ValueError
                count += 1
                index = whitespace(value(index, depth + 1))
                if index < length and text[index] == ']':
                    return index + 1
                if index >= length or text[index] != ',':
                    raise ValueError
                index = whitespace(index + 1)
            raise ValueError
        for literal in ('true', 'false', 'null'):
            if text.startswith(literal, index):
                return index + len(literal)
        match = re.match(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?', text[index:index + 33])
        if match is None or len(match[0]) > 32:
            raise ValueError
        if not any(char in match[0] for char in '.eE'):
            _int_token(match[0])
        return index + len(match[0])

    if whitespace(value(0, 0)) != length:
        raise ValueError


def decode_fixture(frame, limit=65536):
    """Bound frame, lexical depth/token sizes, then decode and bound every node."""
    if type(frame) is not bytes or len(frame) > limit:
        raise ValueError
    text = frame.decode('utf-8')
    _preflight_json(text)
    result = json.loads(text, object_pairs_hook=_pairs, parse_int=_int_token,
                        parse_constant=lambda value: (_ for _ in ()).throw(ValueError()))
    pending = [(result, 0)]
    nodes = 0
    while pending:
        value, level = pending.pop()
        nodes += 1
        if nodes > 8192 or level > 8:
            raise ValueError
        kind = type(value)
        if kind is str:
            if len(value) > 128 or len(value.encode('utf-8')) > 128:
                raise ValueError
        elif kind is dict:
            pending.extend((key, level + 1) for key in value)
            pending.extend((item, level + 1) for item in value.values())
        elif kind is list:
            if len(value) > 128:
                raise ValueError
            pending.extend((item, level + 1) for item in value)
        elif kind is float:
            if not isfinite(value):
                raise ValueError
        elif value is not None and kind is not bool and kind is not int:
            raise ValueError
    return result


def _size(value):
    return (type(value) is dict and set(value) == {'width', 'height'}
            and _integer(value['width'], 1, 16384)
            and _integer(value['height'], 1, 16384))


def parse_kscreen(frame, profile):
    if profile is not KScreenProfile.SYNTHETIC_V1:
        return ParseResult(reasons=('kscreen_profile_unverified',))
    try:
        raw = decode_fixture(frame)
        return _parse(raw)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return ParseResult(reasons=('kscreen_schema_invalid',))


def _parse(raw):
    if type(raw) is not dict or 'outputs' not in raw:
        raise ValueError
    outputs = raw['outputs']
    if type(outputs) is not list or len(outputs) > 16:
        raise ValueError
    parsed, ids, names, references = [], set(), set(), []
    for item in outputs:
        if type(item) is not dict:
            raise ValueError
        required = {'id', 'name', 'connected', 'enabled', 'scale', 'rotation',
                    'clones', 'replicationSource'}
        if not required <= set(item):
            raise ValueError
        number, name = item['id'], item['name']
        if (not _integer(number, 1, 2147483647) or number in ids
                or type(name) is not str or len(name) > 24
                or re.fullmatch(CONNECTOR, name) is None or name in names
                or type(item['connected']) is not bool or type(item['enabled']) is not bool
                or item['enabled'] and not item['connected']
                or not _number(item['scale'], 0.25, 8)
                or not _integer(item['rotation'], 1, 8)
                or item['rotation'] not in (1, 2, 4, 8)):
            raise ValueError
        clones, replication = item['clones'], item['replicationSource']
        if (type(clones) is not list or len(clones) > 16
                or any(not _integer(value, 1, 2147483647) for value in clones)
                or len(set(clones)) != len(clones)
                or not _integer(replication, 0, 2147483647)):
            raise ValueError
        references.extend(clones)
        if replication:
            references.append(replication)
        modes = item.get('modes', [])
        if type(modes) is not list or len(modes) > 128:
            raise ValueError
        mode_ids = set()
        for mode in modes:
            if (type(mode) is not dict or type(mode.get('id')) is not str
                    or not mode['id'] or mode['id'] in mode_ids
                    or not _size(mode.get('size'))
                    or not _number(mode.get('refreshRate'), 0.001, 1000)):
                raise ValueError
            mode_ids.add(mode['id'])
        rectangle = None
        if item['enabled']:
            position, size = item.get('pos'), item.get('size')
            if (type(position) is not dict or set(position) != {'x', 'y'}
                    or not _integer(position['x'], -32768, 32767)
                    or not _integer(position['y'], -32768, 32767) or not _size(size)
                    or type(item.get('currentModeId')) is not str
                    or item['currentModeId'] not in mode_ids):
                raise ValueError
            rectangle = (position['x'], position['y'], size['width'], size['height'])
        ids.add(number)
        names.add(name)
        parsed.append(KOutput(number, name, item['connected'], item['enabled'],
                              rectangle, bool(clones or replication)))
    if any(value not in ids for value in references):
        raise ValueError
    mirrored = {item.output_id for item in parsed if item.mirrored}
    mirrored.update(references)
    for left in parsed:
        for right in parsed:
            if left.output_id >= right.output_id or left.rectangle is None or right.rectangle is None:
                continue
            x, y, width, height = left.rectangle
            a, b, other_width, other_height = right.rectangle
            if x < a + other_width and a < x + width and y < b + other_height and b < y + height:
                mirrored.update((left.output_id, right.output_id))
    return ParseResult(KScreenData(tuple(KOutput(item.output_id, item.name,
        item.connected, item.enabled, item.rectangle, item.output_id in mirrored)
        for item in sorted(parsed, key=lambda output: output.output_id))))
