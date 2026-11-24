"""Repository-only structural contracts; fixtures never mutate product files.

Live-tree assertions are regression checks, not claimed RED/GREEN cycles.
Only synthetic text/AST fixtures exercise forbidden integrations.
"""

import ast
import configparser
import fnmatch
import importlib.util
import json
from pathlib import Path
import re
import shlex
import unittest
from unittest.mock import patch
import yaml

from tests.test_build_provenance import shell_wiring_content, workflow_wiring_content

ROOT = Path(__file__).resolve().parents[1]
DISPLAY = 'prototype/hybrid-display'
DISPLAY_REF = re.compile(r'(?i)(?<![a-z0-9])hybrid[-_]display(?:[^a-z0-9]|$)')


def mentions_display(content):
    return any(DISPLAY_REF.search(token) for token in content.splitlines()
               if not re.search(r'(?i)\.md(?:#[^\s]*)?$', token.strip()))


def docker_instructions(source):
    pending = ''
    for line in source.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        pending += line.strip()
        if pending.endswith('\\'):
            pending = pending[:-1] + ' '
            continue
        match = re.fullmatch(r'([A-Za-z]+)\s+(.*)', pending)
        if not match:
            raise AssertionError('container-parse: unsupported instruction')
        yield match[1].upper(), match[2]
        pending = ''
    if pending:
        raise AssertionError('container-parse: incomplete continuation')


def container_content(source):
    return '\n'.join(shell_wiring_content(body) for instruction, body in docker_instructions(source)
                     if instruction != 'LABEL')


def covers_display(source):
    source = source.removeprefix('./').rstrip('/')
    return (source in ('', '.') or '..' in Path(source).parts
            or DISPLAY == source or DISPLAY.startswith(source + '/')
            or fnmatch.fnmatchcase(DISPLAY, source)
            or fnmatch.fnmatchcase(DISPLAY + '/src/hybrid_display/model.py', source))


def broad_container_copy(path, source):
    # installer/ is a separate context and cannot contain the repository prototype.
    if path == 'installer/Containerfile':
        return False
    for instruction, body in docker_instructions(source):
        if instruction not in ('COPY', 'ADD'):
            continue
        tokens = shlex.split(body, comments=True)
        if any(token == '--from' or token.startswith('--from=') for token in tokens):
            continue
        operands = re.sub(r'^(?:--[^\s]+\s+)*', '', body)
        args = json.loads(operands) if operands.startswith('[') else shlex.split(operands, comments=True)
        if len(args) < 2:
            raise AssertionError(path + ': release: invalid container copy')
        if any(covers_display(value) for value in args[:-1]):
            return True
    return False


def ini_content(source):
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.optionxform = str
    parser.read_string(source)
    decorative = {'name', 'description', 'comment', 'genericname', 'documentation', 'icon', 'keywords'}
    return '\n'.join(key + '\n' + value for section in parser.sections()
                     for key, value in parser.items(section)
                     if key.split('[')[0].lower() not in decorative)


def python_content(source):
    values = []
    tree = ast.parse(source)
    loaded = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)}

    class Wiring(ast.NodeVisitor):
        data = False

        def visit_Expr(self, node):
            if not isinstance(node.value, ast.Constant) or not isinstance(node.value.value, str):
                self.generic_visit(node)

        def visit_Assign(self, node):
            if all(isinstance(target, ast.Name) and target.id.lower() in
                   {'name', 'description', 'title', '__doc__'} and target.id not in loaded for target in node.targets):
                return
            self.generic_visit(node)

        def visit_Call(self, node):
            self.visit(node.func)
            for argument in node.args:
                self.visit(argument)
            for keyword in node.keywords:
                if keyword.arg in {'description', 'help'}:
                    continue
                previous = self.data
                self.data = previous or keyword.arg in {'env', 'with_', 'services', 'container', 'defaults'}
                self.visit(keyword.value)
                self.data = previous

        def visit_Dict(self, node):
            for key, value in zip(node.keys, node.values):
                if key is not None:
                    self.visit(key)
                self.visit(value)

        def visit_Import(self, node):
            values.extend(alias.name for alias in node.names)

        def visit_ImportFrom(self, node):
            values.append(node.module or '')
            values.extend(alias.name for alias in node.names)

        def visit_Constant(self, node):
            if isinstance(node.value, str):
                values.append(node.value)

    Wiring().visit(tree)
    return '\n'.join(values)


def policy_python_execution_content(source):
    """Follow policy data into imports and unknown/executable consumers.

    Only the explicit policy files use this bounded AST analysis. Exact fields
    stay separate from aggregate reads; finite literal loop keys are resolved.
    Unknown consumers and dynamic keys remain conservative. This is not a
    general Python security analyzer.
    """
    tree = ast.parse(source)
    nodes = list(ast.walk(tree))
    bindings, domains = {}, {}
    assignments = []
    rebound = {node.id for node in nodes if isinstance(node, ast.Name)
               and isinstance(node.ctx, ast.Store)}
    rebound.update(node.arg for node in nodes if isinstance(node, ast.arg))
    rebound.update(ast.unparse(node) for node in nodes
                   if isinstance(node, (ast.Attribute, ast.Subscript))
                   and isinstance(node.ctx, ast.Store))
    for node in nodes:
        if isinstance(node, ast.Import):
            rebound.update(alias.asname or alias.name.split('.')[0] for alias in node.names
                           if alias.asname or alias.name not in {'re', 'json'})
        elif isinstance(node, ast.ImportFrom):
            rebound.update(alias.asname or alias.name for alias in node.names)
        if isinstance(node, ast.Assign):
            assignments.extend((target, node.value) for target in node.targets)
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr, ast.AugAssign)) and node.value is not None:
            assignments.append((node.target, node.value))
        elif isinstance(node, (ast.For, ast.comprehension)):
            assignments.append((node.target, node.iter))
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            rebound.add(node.name)
            assignments.extend((ast.Name(id=node.name), item.value) for item in ast.walk(node)
                               if isinstance(item, ast.Return) and item.value is not None)

    for target, value in assignments:
        if isinstance(target, ast.Name):
            literals = value.elts if isinstance(value, (ast.Tuple, ast.List)) else [value]
            known = all(isinstance(item, ast.Constant) and isinstance(item.value, (str, int))
                        for item in literals)
            if not known or domains.get(target.id) is None and target.id in domains:
                domains[target.id] = None
            else:
                domains.setdefault(target.id, set()).update(item.value for item in literals)

    def field_refs(key):
        found = set(bindings.get(key, ()))
        for name, refs in bindings.items():
            if name.startswith((key + '[', key + '.')):
                found.update(refs)
        return found

    def references(node):
        if isinstance(node, ast.Constant):
            return {node.value} if isinstance(node.value, str) and DISPLAY_REF.search(node.value) else set()
        if isinstance(node, ast.Name):
            return field_refs(node.id)
        if isinstance(node, ast.Subscript):
            base = ast.unparse(node.value)
            keys = ({node.slice.value} if isinstance(node.slice, ast.Constant) else
                    domains.get(node.slice.id) if isinstance(node.slice, ast.Name) else None)
            if keys is not None:
                found = set(bindings.get(base, ()))
                for key in keys:
                    access = ast.Subscript(value=node.value, slice=ast.Constant(value=key))
                    found.update(field_refs(ast.unparse(access)))
                return found
        found = set()
        for child in ast.iter_child_nodes(node):
            found.update(references(child))
        return found

    while True:
        before = {key: set(value) for key, value in bindings.items()}
        for target, value in assignments:
            names = ([target.id] if isinstance(target, ast.Name) else
                     [ast.unparse(target)] if isinstance(target, (ast.Subscript, ast.Attribute)) else
                     [name.id for name in ast.walk(target) if isinstance(name, ast.Name)])
            for name in names:
                # Preserve known field structure across aliases and returned
                # dictionaries; do not flatten a summary into every bool field.
                origin = (value.id if isinstance(value, ast.Name) else
                          value.func.id if isinstance(value, ast.Call)
                          and isinstance(value.func, ast.Name) else None)
                fields = {key[len(origin):]: set(refs) for key, refs in bindings.items()
                          if origin and key.startswith((origin + '[', origin + '.'))}
                refs = bindings.get(origin, set()) if fields else references(value)
                bindings.setdefault(name, set()).update(refs)
                for suffix, refs in fields.items():
                    bindings.setdefault(name + suffix, set()).update(refs)
        if before == bindings:
            break

    data_calls = {'path.startswith', 'path.endswith', 're.fullmatch', 're.search',
                  'str', 'repr', 'bool', 'len', 'list', 'tuple', 'set', 'dict', 'sorted',
                  'json.dumps', 'print', 'policy.path_class', 'policy.classify',
                  'self.policy.path_class', 'self.policy.classify'}
    dicts = {target.id for target, value in assignments if isinstance(target, ast.Name)
             and (isinstance(value, ast.Dict) or isinstance(value, ast.Call)
                  and isinstance(value.func, ast.Name) and value.func.id == 'dict')}
    execution = []
    for node in nodes:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            execution.extend(alias.name for alias in node.names)
            if isinstance(node, ast.ImportFrom):
                execution.append(node.module or '')
        elif isinstance(node, ast.Call):
            callee = ast.unparse(node.func)
            root = callee.split('.')[0]
            assertion = (isinstance(node.func, ast.Attribute)
                         and isinstance(node.func.value, ast.Name)
                         and node.func.value.id == 'self'
                         and node.func.attr.startswith('assert'))
            dict_operation = (isinstance(node.func, ast.Attribute)
                              and isinstance(node.func.value, ast.Name)
                              and node.func.value.id in dicts
                              and node.func.attr in {'get', 'items', 'keys', 'values', 'update', 'setdefault'})
            if dict_operation and node.func.attr in {'update', 'setdefault'}:
                # Unknown mutation shapes are not silently exempted.
                dict_operation = not any(references(argument) for argument in
                    [*node.args, *(keyword.value for keyword in node.keywords)])
            path_predicate = callee in {'path.startswith', 'path.endswith'}
            if callee not in rebound and (
                (callee in data_calls and (root not in rebound or path_predicate)) or assertion or dict_operation
            ):
                continue
            execution.append(callee)
            # A function's return value is data until passed to a consumer.
            # Receiver references still matter (e.g. Path(...).write_text()).
            consumed = set()
            if isinstance(node.func, ast.Attribute):
                consumed.update(references(node.func.value))
            for argument in [*node.args, *(keyword.value for keyword in node.keywords)]:
                consumed.update(references(argument))
            execution.extend('execution argument: ' + ref + ' (consumed)' for ref in sorted(consumed))
    return '\n'.join(execution)


def javascript_content(source):
    # A lexical scan, not a JS evaluator; preserve strings containing // or /*.
    string = r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|`(?:\\.|[^`\\])*`'''
    tokens = re.compile(string + r'|//[^\n]*|/\*[\s\S]*?\*/')
    clean = tokens.sub(lambda match: '\n' * match[0].count('\n')
                       if match[0].startswith(('//', '/*')) else match[0], source)
    for field in ('name', 'description', 'title'):
        # Only an isolated metadata declaration is decorative. References to the
        # identifier/property elsewhere make its value potentially functional.
        outside_strings = re.sub(string, '', clean)
        if len(re.findall(r'\b' + field + r'\b', outside_strings)) == 1:
            clean = re.sub(r'\b' + field + r'\s*(?::[^=;\n]+)?=\s*(?:' + string + ')', '', clean)
            clean = re.sub(r'\b' + field + r'\s*:\s*(?:' + string + ')', '', clean)
    values = [match[0][1:-1] for match in re.finditer(string, clean)]
    values.append(re.sub(string, '', clean))
    return '\n'.join(values)


def workflow_content(source):
    content = [workflow_wiring_content(source)]
    # The shared helper ignores name/description outside known data contexts.
    # Preserve those keys in opaque/future functional fields as well.
    def scalars(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield str(key)
                yield from scalars(value)
        elif isinstance(node, list):
            for value in node:
                yield from scalars(value)
        elif node is not None:
            yield str(node)

    def walk(node, path=()):
        if isinstance(node, dict):
            opaque = any(part in {'with', 'env', 'services', 'container', 'defaults', 'matrix'} for part in path)
            metadata = not opaque and (not path or (len(path) == 2 and path[0] == 'jobs')
                       or (len(path) >= 2 and path[-2] in {'steps', 'inputs', 'outputs'}))
            for key, value in node.items():
                if key in {'name', 'description'} and not metadata:
                    content.extend(scalars(value))
                walk(value, path + (key,))
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, path + (index,))

    walk(yaml.safe_load(source))
    return '\n'.join(content)


def wiring_violations(path, source, contract='release'):
    if 'Containerfile' in Path(path).name:
        content = container_content(source)
    elif path.endswith('.py'):
        policy_files = {'scripts/classify-container-changes.py',
                        'tests/test_container_workflow_policy.py',
                        'tests/test_hybrid_display_safety.py'}
        content = (policy_python_execution_content(source) if path in policy_files
                   else python_content(source))
    elif path.endswith(('.js', '.jsx', '.ts', '.tsx', '.mjs', '.cjs')):
        content = javascript_content(source)
    elif path.endswith(('.service', '.desktop', '.conf', '.override', '.rules')) and re.search(r'^\s*\[', source, re.M):
        content = ini_content(source)
    else:
        content = workflow_content(source) if path.endswith(('.yml', '.yaml', '.json')) else shell_wiring_content(source)
    wired = mentions_display(content)
    if 'Containerfile' in Path(path).name:
        wired = wired or broad_container_copy(path, source)
    return [f'{path}: {contract}: hybrid-display execution reference'] if wired else []


def outer_capability_violations(path, tree):
    """Exact prototype exception, never a general subprocess/host exemption."""
    errors = set()
    parents, scopes = {}, {}
    def visit(node, scope=''):
        if isinstance(node, ast.ClassDef):
            scope = node.name
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            scope = (scope + '.' if scope else '') + node.name
        scopes[node] = scope
        for child in ast.iter_child_nodes(node):
            parents[child] = node
            visit(child, scope)
    visit(tree)
    imports = {'sys', 'pathlib', 'argparse', 'json', 'os', 'pwd', 're', 'secrets',
               'select', 'signal', 'stat', 'subprocess', 'time',
               'hybrid_display.outer_session', 'hybrid_display.outer_supervisor'}
    opens = {'directory', 'PrivateTree.create', 'PrivateTree._purge', '_System._read', '_System.receipt'}
    spawns = {'_System.kwin', '_Child.query', '_Child.start'}
    prohibited = {'exec', 'eval', 'compile', '__import__', 'globals', 'locals',
                  'read_text', 'read_bytes', 'write_text', 'write_bytes', 'system',
                  'popen', 'fork', 'kill', 'spawnv', 'spawnve', 'makedirs', 'rmtree',
                  'rename', 'replace', 'chmod', 'chown', 'symlink'}
    for node in ast.walk(tree):
        scope = scopes[node]
        if isinstance(node, ast.Attribute) and ast.unparse(node) == 'subprocess.Popen':
            parent = parents.get(node)
            assignment = parents.get(parent)
            if (scope != '_System.__init__' or not isinstance(parent, ast.IfExp)
                    or not isinstance(assignment, ast.Assign)
                    or len(assignment.targets) != 1
                    or ast.unparse(assignment.targets[0]) != 'self.spawn'):
                errors.add('spawn-alias')
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [x.name for x in node.names] if isinstance(node, ast.Import) else [node.module]
            if any(x not in imports for x in modules) or any(x.asname for x in node.names):
                errors.add('import')
            if isinstance(node, ast.ImportFrom) and node.module not in {
                    'pathlib', 'hybrid_display.outer_session', 'hybrid_display.outer_supervisor'}:
                errors.add('import-from')
        if isinstance(node, ast.Attribute) and ast.unparse(node.value) == 'os' and node.attr == 'environ':
            parent = parents.get(node)
            if not isinstance(parent, ast.Attribute) or parent.attr != 'get':
                errors.add('whole-environment')
        if not isinstance(node, ast.Call):
            continue
        callee = ast.unparse(node.func)
        leaf = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
        if leaf in prohibited or callee.startswith('subprocess.'):
            errors.add('execution')
        if callee == 'os.environ.get':
            valid = False
            if scope == '_System.child_display' and len(node.args) == 1:
                valid = isinstance(node.args[0], ast.Constant) and node.args[0].value == 'WAYLAND_DISPLAY'
            elif scope == '_System.__init__' and len(node.args) == 1:
                ancestor = parents.get(node)
                while ancestor is not None and not isinstance(ancestor, ast.DictComp):
                    ancestor = parents.get(ancestor)
                if isinstance(ancestor, ast.DictComp) and len(ancestor.generators) == 1:
                    expected = "('XDG_RUNTIME_DIR', 'XDG_SESSION_ID', 'XDG_SESSION_TYPE')"
                    valid = ast.unparse(ancestor.generators[0].iter) == expected and ast.unparse(node.args[0]) == 'k'
            if not valid:
                errors.add('environment-name')
        if leaf == 'open' and (scope not in opens or callee not in {'fs.open', 'self.fs.open'}):
            errors.add('open')
        if leaf == 'killpg' and (scope != 'OwnedGroup.close' or callee != 'self.kernel.killpg'
                or len(node.args) != 2 or ast.unparse(node.args[0]) != 'self.process.pid'
                or ast.unparse(node.args[1]) not in {'signal.SIGTERM', '0'}):
            errors.add('signal')
        if leaf in {'mkdir', 'rmdir', 'unlink', 'link', 'write'}:
            allowed = {'mkdir': {'PrivateTree.create'}, 'rmdir': {'PrivateTree.cleanup', 'PrivateTree._purge'},
                       'unlink': {'PrivateTree._purge', '_System.receipt'},
                       'link': {'_System.receipt'}, 'write': {'PrivateTree.create', '_System.receipt'}}
            if scope not in allowed[leaf]:
                errors.add('filesystem-write')
        if leaf in {'spawn', 'Popen'}:
            if (callee not in {'self.spawn', 'self.system.spawn'} or scope not in spawns
                    or not node.args or any(k.arg is None for k in node.keywords)):
                errors.add('spawn')
            elif scope == '_Child.query':
                command = node.args[0]
                if (not isinstance(command, ast.Tuple) or len(command.elts) != 1
                        or not isinstance(command.elts[0], ast.Constant)
                        or command.elts[0].value != '/usr/bin/wayland-info'):
                    errors.add('provider-command')
            elif scope == '_System.kwin' and not (isinstance(node.args[0], ast.Call) and ast.unparse(node.args[0].func) == 'kwin_argv'):
                errors.add('kwin-command')
            elif scope == '_Child.start' and ast.unparse(node.args[0]) != 'argv':
                errors.add('payload-command')
        if any(k.arg == 'shell' and not (isinstance(k.value, ast.Constant) and k.value.value is False) for k in node.keywords):
            errors.add('shell')
    return [path + ': bounded-outer: ' + reason for reason in sorted(errors)]


def product_violations(path, source):
    tree = ast.parse(source, filename=path)
    errors = set()
    outer = path == DISPLAY + '/outer-kwin-session.py'
    if outer:
        errors.update(outer_capability_violations(path, tree))
    forbidden_imports = {'os', 'sys', 'subprocess', 'signal', 'socket', 'pathlib',
                         'psutil', 'threading', 'multiprocessing', 'requests', 'urllib',
                         'http', 'dbus', 'systemd', 'ctypes', 'builtins', 'importlib', 'io'}
    forbidden_calls = {'open', 'exec', 'eval', 'compile', '__import__', 'globals', 'locals',
                       'read_text', 'read_bytes', 'write_text', 'write_bytes', 'Popen',
                       'system', 'popen', 'fork', 'kill', 'killpg', 'spawnv', 'spawnve',
                       'trigger_hotplug', 'create_lease', 'drmModeAtomicCommit',
                       'drmModeSetCrtc', 'enable_output', 'disable_output', 'set_output_enabled'}
    for node in ast.walk(tree):
        modules = ([alias.name for alias in node.names] if isinstance(node, ast.Import)
                   else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
        if not outer and any(module.split('.')[0] in forbidden_imports for module in modules):
            errors.add(f'{path}: pure-library: forbidden host import')
        if any(re.search(r'(?i)hybrid[-_]focus|inputplumber|decky', module) for module in modules):
            errors.add(f'{path}: no-focus: focus, profile or Decky import')
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else node.func.attr if isinstance(node.func, ast.Attribute) else ''
            if not outer and name in forbidden_calls:
                errors.add(f'{path}: pure-library: host or dynamic execution call')
        if not outer and isinstance(node, ast.If) and any(
                isinstance(value, ast.Constant) and value.value == '__main__' for value in ast.walk(node.test)):
            errors.add(f'{path}: no-launcher: Python main guard')
    functional = python_content(source)
    focus_content = '\n'.join(value for value in functional.splitlines()
                              if value not in {'decky_active', 'focus_integration_active'})
    if re.search(r'(?i)hybrid[-_]focus|inputplumber|decky', focus_content):
        errors.add(f'{path}: no-focus: focus, profile or Decky reference')
    if re.search(r'(?i)/sys/(?:class/drm|kernel/debug)(?:/|\b)|'
                 r'\b(?:kscreen-doctor|wlr-randr|xrandr|loginctl|systemctl|busctl|OutputManager)\b|'
                 r'\b(?:WLR_DRM_DEVICES|DRI_PRIME|MESA_VK_DEVICE_SELECT|VK_ICD_FILENAMES|AMD_VULKAN_ICD)\b', functional):
        errors.add(f'{path}: no-hardware: control path, tool or GPU override')
    return sorted(errors)


def launcher_violations(paths, executable=()):
    errors = []
    for path in sorted(paths):
        name = Path(path).name
        if (path == 'bin' or path.startswith('bin/')
                or name in {'install-user.sh', 'uninstall-user.sh', 'pyproject.toml',
                            'setup.py', 'setup.cfg', 'package.json'}
                or path.endswith(('.service', '.socket', '.timer', '.target', '.desktop'))
                or path in executable and path != 'outer-kwin-session.py'):
            errors.append(f'{DISPLAY}/{path}: no-launcher: installable or executable artifact')
    return errors


def read_repo(relative):
    target = ROOT / relative
    if not target.resolve().is_relative_to(ROOT):
        raise AssertionError(f'{relative}: repository-scope: outside repository')
    return target.read_text()


def files_under(*roots):
    for relative in roots:
        target = ROOT / relative
        if target.is_file():
            yield relative
        elif target.is_dir():
            yield from sorted(str(path.relative_to(ROOT)) for path in target.rglob('*') if path.is_file())


def check_sources(paths, contract):
    errors = []
    for relative in sorted(set(paths)):
        if Path(relative).suffix.lower() in {'.md', '.png', '.jpg', '.jxl', '.svg', '.css', '.der'}:
            continue
        try:
            errors.extend(wiring_violations(relative, read_repo(relative), contract))
        except (AssertionError, SyntaxError, ValueError, configparser.Error) as error:
            errors.append(f'{relative}: {contract}: cannot parse functional source ({type(error).__name__})')
    return errors


def readme_issues(source):
    text = re.sub(r'\s+', ' ', re.sub(r'[`*_]', '', source).casefold())
    clauses = re.split(r'[.!?]', text)
    required = {
        'non_executable': bool(re.search(r'\bnicht ausführbar\w*\b|\bkein\w* ausführbar\w* launcher\b', text)),
        'no_os_adapter': bool(re.search(r'\bkein\w* betriebssystemadapter\b|betriebssystemadapter[^.!?]{0,40}nicht vorhanden', text)),
        'no_hardware_validation': bool(re.search(r'\bkeine hardwarevalidierung\b|\bnicht hardwarevalidiert\b|tests ersetzen keine hardwareabnahme', text)),
        'no_release_iso': any(re.search(r'\b(?:keine|ohne|nicht)\b', clause)
                             and all(term in clause for term in ('release', 'iso'))
                             and ('integration' in clause or 'einbindung' in clause) for clause in clauses),
        'no_controller_focus': bool(re.search(r'\bkeine controller[- ]fokus\w*\b|controller[- ]fokus[^.!?]{0,40}nicht (?:implementiert|vorhanden|enthalten)', text)),
        'separate_hardware': any('dell' in clause and 'hp' in clause
                                and re.search(r'getrennt|separat|eigenständig', clause)
                                and re.search(r'abnahme|hardwaretest|validierung', clause) for clause in clauses),
    }
    return [f'{DISPLAY}/README.md: readme-{name}: missing boundary'
            for name, present in required.items() if not present]


def current_readme():
    path = ROOT / DISPLAY / 'README.md'
    return read_repo(DISPLAY + '/README.md') if path.exists() else ''


class ReadmeContracts(unittest.TestCase):
    def test_classifier_category_h_is_tests_only_without_product_integration(self):
        text = re.sub(r'\s+', ' ', current_readme().replace('`', '').casefold())
        label = DISPLAY + '/README.md: classifier-documentation: '
        self.assertRegex(text, r'\bkategorie h\b', label + 'expected H, not the outdated unknown G policy')
        for path in ('prototype/hybrid-display/**', 'tests/test_hybrid_display_*.py'):
            self.assertIn(path, text, label + 'missing prototype/test scope')
        clauses = re.split(r'[.!?]', text)
        self.assertTrue(any('h-only' in clause and 'tests-only' in clause for clause in clauses), label + 'H-only')
        for effect in ('containerbau', 'publish', 'iso-lauf'):
            self.assertTrue(any(re.search(r'\bkein\w*\b', clause) and effect in clause
                                and 'h-only' in clause for clause in clauses), label + effect)
        self.assertTrue(any('classifier' in clause and 'keine' in clause
                            and all(term in clause for term in ('produkt-', 'session-', 'releaseintegration'))
                            for clause in clauses), label + 'classification is not integration')

    def test_safe_editorial_changes_and_relative_links(self):
        source = current_readme()
        self.assertEqual(readme_issues(source.replace('\n', '  \n') + '\nWeitere sichere Dokumentation.\n'), [])
        for target in re.findall(r'\]\(([^)]+)\)', source):
            resolved = (ROOT / DISPLAY / target).resolve()
            self.assertTrue(resolved.is_relative_to(ROOT), DISPLAY + '/README.md: readme-link: scope')
            self.assertTrue(resolved.is_file(), DISPLAY + '/README.md: readme-link: missing ' + target)

    def test_non_executable_boundary(self):
        self.assertFalse(any('readme-non_executable:' in error for error in readme_issues(current_readme())))

    def test_no_os_adapter_boundary(self):
        self.assertFalse(any('readme-no_os_adapter:' in error for error in readme_issues(current_readme())))

    def test_no_hardware_validation_boundary(self):
        self.assertFalse(any('readme-no_hardware_validation:' in error for error in readme_issues(current_readme())))

    def test_no_release_iso_boundary(self):
        self.assertFalse(any('readme-no_release_iso:' in error for error in readme_issues(current_readme())))

    def test_no_controller_focus_boundary(self):
        self.assertFalse(any('readme-no_controller_focus:' in error for error in readme_issues(current_readme())))

    def test_separate_hardware_boundary(self):
        self.assertFalse(any('readme-separate_hardware:' in error for error in readme_issues(current_readme())))


class RepositoryRegressionTests(unittest.TestCase):
    """Already-correct repository state: regression evidence, not RED/GREEN."""

    def test_classifier_display_paths_are_isolated_tests_only_without_git_execution(self):
        relative = 'scripts/classify-container-changes.py'
        spec = importlib.util.spec_from_file_location('display_safety_classifier', ROOT / relative)
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        paths = [DISPLAY + '/src/hybrid_display/model.py', DISPLAY + '/src/hybrid_display/cli.py',
                 'tests/test_hybrid_display_cli.py', DISPLAY + '/README.md']
        base, head = 'a' * 40, 'b' * 40  # Synthetic revisions; no historical baseline.

        def fake_git(repo, *args):
            if args in [('cat-file', '-e', base + '^{commit}'),
                        ('cat-file', '-e', head + '^{commit}'),
                        ('merge-base', '--is-ancestor', base, head)]:
                return b''
            if args == ('diff', '--no-ext-diff', '--name-status', '-z', '--find-renames', base, head, '--'):
                return ''.join('A\0' + path + '\0' for path in paths).encode()
            self.fail(relative + ': classifier: unexpected Git request')

        with patch.object(policy, 'git', side_effect=fake_git):
            first = policy.classify(ROOT, 'push', base, head, 'refs/heads/main')
            paths.reverse()
            second = policy.classify(ROOT, 'push', base, head, 'refs/heads/main')
        for result in (first, second):
            self.assertFalse(result['blocking'], relative + ': classifier: isolated display must run tests')
            self.assertEqual(result['unknown'], [])
            self.assertTrue(result['run_tests'])
            self.assertEqual(result['classes'], ['H'])
            for key in ('build_container', 'release_candidate', 'run_iso'):
                self.assertFalse(result[key], relative + ': classifier: ' + key)
        self.assertEqual(first['unknown'], second['unknown'])
        self.assertEqual(policy.path_class('docs/superpowers/specs/example.md'), 'E')
        self.assertEqual(policy.path_class(DISPLAY + '/README.md'), 'H')

    def test_classifier_unknown_and_display_mixed_paths_remain_blocked(self):
        spec = importlib.util.spec_from_file_location(
            'display_unknown_policy', ROOT / 'scripts/classify-container-changes.py')
        policy = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(policy)
        unknown = 'experimental/unclassified-feature.txt'
        for paths in ([unknown], [DISPLAY + '/README.md', unknown]):
            def fake_git(repo, *args):
                if args[0] in {'cat-file', 'merge-base'}:
                    return b''
                self.assertEqual(args[0], 'diff')
                return ''.join('A\0' + path + '\0' for path in paths).encode()

            with patch.object(policy, 'git', side_effect=fake_git):
                result = policy.classify(ROOT, 'push', 'a' * 40, 'b' * 40, 'refs/heads/main')
            self.assertTrue(result['blocking'])
            self.assertIn('G', result['classes'])
            self.assertEqual(result['unknown'], [unknown])
            for key in ('run_tests', 'build_container', 'release_candidate', 'run_iso'):
                self.assertFalse(result[key], key)

    def test_release_and_payload_sources_have_no_display_integration(self):
        paths = files_under('Containerfile', 'Justfile', 'image-lock.json', 'image-template.env',
                            'build-version.json', 'build_files', 'system_files', 'installer',
                            'disk_config', 'scripts', '.github/workflows', '.github/actions',
                            'pyproject.toml', 'setup.py', 'setup.cfg', 'package.json')
        self.assertEqual(check_sources(paths, 'no-release'), [])

    def test_session_files_and_hooks_have_no_display_integration(self):
        self.assertEqual(check_sources(files_under('system_files', 'installer/system_files'), 'no-session'), [])

    def test_focus_decky_and_profiles_do_not_reference_display(self):
        self.assertEqual(check_sources(files_under('prototype/hybrid-focus'), 'no-focus'), [])

    def test_product_is_pure_non_executable_and_separate_from_focus(self):
        root = ROOT / DISPLAY
        paths = sorted(str(path.relative_to(root)) for path in root.rglob('*'))
        executable = [str(path.relative_to(root)) for path in root.rglob('*')
                      if path.is_file() and path.stat().st_mode & 0o111]
        self.assertEqual(launcher_violations(paths, executable), [])
        errors = []
        for path in sorted(root.rglob('*.py')):
            relative = str(path.relative_to(ROOT))
            errors.extend(product_violations(relative, read_repo(relative)))
        self.assertEqual(errors, [])


class StructuralFixtures(unittest.TestCase):
    def test_only_exact_outer_launcher_has_bounded_host_capabilities(self):
        path = DISPLAY + '/outer-kwin-session.py'
        source = read_repo(path)
        self.assertEqual(product_violations(path, source), [])
        self.assertTrue(product_violations(DISPLAY + '/outer-kwin-session-copy.py', source))
        self.assertEqual(launcher_violations(['outer-kwin-session.py'], ['outer-kwin-session.py']), [])

    def test_outer_exception_rejects_free_commands_signals_and_environment(self):
        path = DISPLAY + '/outer-kwin-session.py'
        source = read_repo(path)
        for unsafe in (source + '\nsubprocess.run(["/bin/sh", "-c", "bad"])\n',
                       source + '\nenv = dict(os.environ)\n',
                       source.replace("('/usr/bin/wayland-info',)", "('/bin/sh',)"),
                       source.replace("('/usr/bin/wayland-info',)", 'request'),
                       source.replace("os.environ.get('WAYLAND_DISPLAY')", "os.environ.get('LD_PRELOAD')"),
                       source + '\nforeign_spawn = subprocess.Popen\n',
                       source.replace('self.kernel.killpg(self.process.pid, signal.SIGTERM)',
                                      'self.kernel.killpg(12345, signal.SIGTERM)'),
                       source.replace('self.kernel.killpg(self.process.pid, signal.SIGTERM)',
                                      'self.kernel.killpg(self.process.pid, signal.SIGKILL)')):
            try:
                errors = product_violations(path, unsafe)
            except (ValueError, TypeError):
                self.fail('Unknown command shape escaped the Safety rejection boundary')
            self.assertTrue(errors)

    def test_private_kwin_resource_is_disabled_without_private_activation(self):
        metadata = json.loads(read_repo(DISPLAY + '/session/kwin/outer-placement/metadata.json'))
        self.assertIs(metadata['KPlugin']['EnabledByDefault'], False)
        self.assertEqual(metadata['KPlugin']['Id'], 'hybrid-display-outer-placement')
        self.assertTrue(launcher_violations(['session/bazzite-hybrid-display-outer-kwin.service']))

    def test_policy_path_rules_are_data_only_in_explicit_policy_files(self):
        source = (
            "def path_class(path):\n"
            "    if path.startswith('prototype/hybrid-display/'):\n"
            "        return 'H'\n"
            "    return 'G'\n"
        )
        for path in ('scripts/classify-container-changes.py',
                     'tests/test_container_workflow_policy.py',
                     'tests/test_hybrid_display_safety.py'):
            with self.subTest(path=path):
                self.assertEqual(wiring_violations(path, source), [])
        self.assertTrue(wiring_violations('scripts/build.py', source))

    def test_policy_test_path_fixtures_are_not_runtime_integration(self):
        source = (
            "paths = ['prototype/hybrid-display/src/hybrid_display/cli.py',\n"
            "         'tests/test_hybrid_display_cli.py']\n"
            "self.assertEqual(policy.path_class(paths[0]), 'H')\n"
        )
        for path in ('tests/test_container_workflow_policy.py', 'tests/test_hybrid_display_safety.py'):
            self.assertEqual(wiring_violations(path, source), [])

    def test_policy_files_still_reject_imports_calls_and_indirect_execution(self):
        for source in (
            'import hybrid_display.cli\n',
            'from hybrid_display import cli\n',
            "import importlib\nimportlib.import_module('hybrid_display.cli')\n",
            "import subprocess\nsubprocess.run(['python3', '-m', 'hybrid_display.cli'])\n",
            "import os\nos.system('python3 prototype/hybrid-display/cli.py')\n",
            "exec('import hybrid_display.cli')\n",
            "argv = ['python3', 'prototype/hybrid-display/cli.py']\nsubprocess.run(argv)\n",
            "target = 'prototype/hybrid-display/cli.py'\nlauncher(target)\n",
            "unit = '[Service]\\nExecStart=hybrid-display-run'\nPath('display.service').write_text(unit)\n",
        ):
            for path in ('scripts/classify-container-changes.py',
                         'tests/test_container_workflow_policy.py',
                         'tests/test_hybrid_display_safety.py'):
                with self.subTest(path=path, source=source):
                    self.assertTrue(wiring_violations(path, source))

    def test_runtime_payload_session_and_workflow_references_still_rejected(self):
        for path, source in (
            ('system_files/usr/bin/start.py', "target = 'prototype/hybrid-display/cli.py'\n"),
            ('installer/install.py', "payload = 'prototype/hybrid-display'\n"),
            ('system_files/display.service', '[Service]\nExecStart=hybrid-display-run\n'),
            ('system_files/etc/gamescope-session-plus/sessions.d/steam', 'exec hybrid-display-run\n'),
            ('Containerfile', 'COPY prototype/hybrid-display /payload\n'),
            ('Containerfile', 'ADD prototype/hybrid-display /payload\n'),
            ('Containerfile', 'RUN python3 -m hybrid_display.cli\n'),
            ('.github/workflows/example.yml', 'jobs:\n  build:\n    steps:\n      - run: python3 -m hybrid_display.cli\n'),
            ('.github/workflows/example.yml', 'run: cp -r prototype/hybrid-display /payload\n'),
            ('installer/build.sh', 'install prototype/hybrid-display/cli.py /usr/bin/display\n'),
        ):
            with self.subTest(path=path):
                self.assertTrue(wiring_violations(path, source))

    def test_policy_execution_cannot_hide_in_mutation_returns_or_shadowed_calls(self):
        cases = (
            "argv = ['python3', '-m', '']\nargv[2] = 'hybrid_display.cli'\nsubprocess.run(argv)\n",
            "command = 'python3 '\ncommand += 'prototype/hybrid-display/cli.py'\nos.system(command)\n",
            "def module_name():\n    return 'hybrid_display.cli'\nimportlib.import_module(module_name())\n",
            "print = subprocess.run\nprint(['python3', '-m', 'hybrid_display.cli'])\n",
            "def execute(print):\n    print(['python3', '-m', 'hybrid_display.cli'])\n",
            "import subprocess as re\nre.fullmatch('hybrid_display.cli')\n",
            "re.fullmatch = subprocess.run\nre.fullmatch(['python3', '-m', 'hybrid_display.cli'])\n",
            "subprocess.run(['/usr/bin/hybrid-display'])\n",
            "os.system('exec hybrid-display')\n",
            "subprocess.run(['python3', 'hybrid-display.py'])\n",
            "p = {}\np.update(module='hybrid_display.cli')\nimportlib.import_module(p['module'])\n",
            "p = {}\np.setdefault('module', 'hybrid_display.cli')\nimportlib.import_module(p['module'])\n",
        )
        for path in ('scripts/classify-container-changes.py',
                     'tests/test_container_workflow_policy.py',
                     'tests/test_hybrid_display_safety.py'):
            for source in cases:
                with self.subTest(path=path, source=source):
                    self.assertTrue(wiring_violations(path, source))

    def test_policy_field_reads_and_finite_output_keys_remain_data(self):
        source = (
            "result = {}\n"
            "result['summary'] = 'Policy for prototype/hybrid-display/cli.py'\n"
            "result['run_tests'] = True\n"
            "for key in ('run_tests', 'run_iso'):\n"
            "    stream.write(str(result[key]))\n"
        )
        self.assertEqual(wiring_violations('scripts/classify-container-changes.py', source), [])
        for extra in ("subprocess.run(result)\n", "subprocess.run(result['summary'])\n",
                      "stream.write(result[unknown_key])\n"):
            self.assertTrue(wiring_violations('scripts/classify-container-changes.py', source + extra))

    def test_python_keyword_dictionary_can_be_functional(self):
        self.assertTrue(wiring_violations('scripts/build.py',
            "import importlib\nimportlib.import_module(**{'name': 'hybrid_display.cli'})"))

    def test_metadata_variables_used_by_execution_are_functional(self):
        cases = [('scripts/build.py', "description='prototype/hybrid-display/cli.py'\nsubprocess.run(['python3', description])"),
                 ('prototype/hybrid-focus/plugin.js', "const description='prototype/hybrid-display/cli.py'; require(description);")]
        for path, source in cases:
            with self.subTest(path=path):
                self.assertTrue(wiring_violations(path, source))

    def test_only_proven_installer_context_excludes_repository_root_copy(self):
        self.assertTrue(wiring_violations('build_files/Containerfile.future', 'COPY . /payload'))
        self.assertEqual(wiring_violations('installer/Containerfile', 'COPY . /payload'), [])

    def test_product_host_imports_and_python_entrypoints_are_forbidden(self):
        for source in ('import subprocess\n', 'from os import system as invoke\n',
                       'from signal import SIGTERM\n', 'open("file")\n',
                       'if __name__ == "__main__":\n    main()\n'):
            errors = product_violations('prototype/hybrid-display/src/hybrid_display/new.py', source)
            self.assertTrue(errors, source)
            self.assertIn('prototype/hybrid-display/src/hybrid_display/new.py:', errors[0])

    def test_workflow_execution_fields_detect_integration(self):
        for source in ('jobs:\n  payload:\n    steps:\n      - run: install prototype/hybrid-display /payload\n',
                       'env:\n  HYBRID_DISPLAY: enabled\n',
                       'uses: ./prototype/hybrid-display\n'):
            errors = wiring_violations('.github/workflows/example.yml', source)
            self.assertTrue(errors, 'Functional workflow wiring must be rejected')
            self.assertIn('.github/workflows/example.yml: release:', errors[0])


    def test_container_metadata_is_documentation_not_payload_wiring(self):
        source = '# COPY prototype/hybrid-display /payload\nLABEL description="prototype/hybrid-display"\n'
        self.assertEqual(wiring_violations('Containerfile', source), [])
        for instruction in ('COPY prototype/hybrid-display /payload',
                            'ADD ["prototype/hybrid-display", "/payload"]',
                            'RUN python3 prototype/hybrid-display/run.py'):
            self.assertTrue(wiring_violations('Containerfile', instruction))


    def test_broad_root_container_copy_cannot_silently_include_prototype(self):
        for source in ('COPY . /payload', 'COPY prototype /payload',
                       'COPY ["prototype/", "/payload/"]', 'ADD * /payload',
                       'COPY prototype/* /payload'):
            self.assertTrue(wiring_violations('Containerfile', source), source)
        self.assertEqual(wiring_violations('installer/Containerfile', 'COPY . /installer'), [])
        self.assertEqual(wiring_violations('Containerfile', 'COPY build_files /build'), [])
        self.assertEqual(wiring_violations('Containerfile', 'COPY --from=base / /payload'), [])


    def test_service_and_desktop_names_are_not_executable_fields(self):
        for path, source in (
            ('system_files/test.service', '[Unit]\nDescription=hybrid-display discussion\n[Service]\nExecStart=/usr/bin/true\n'),
            ('system_files/test.desktop', '[Desktop Entry]\nName=hybrid-display discussion\nComment=hybrid-display\nExec=/usr/bin/true\n')):
            self.assertEqual(wiring_violations(path, source, 'session'), [])
        for path, source in (
            ('system_files/test.service', '[Service]\nExecStart=hybrid-display-run\n'),
            ('system_files/test.desktop', '[Desktop Entry]\nExec=hybrid-display-run\n'),
            ('system_files/test.conf', '[Autologin]\nSession=hybrid-display\n'),
            ('system_files/test.service', '[Unit]\nWants=hybrid-display.service\n')):
            self.assertTrue(wiring_violations(path, source, 'session'))


    def test_python_docstrings_and_descriptions_are_not_cross_imports(self):
        source = '"""hybrid_display is deliberately not used."""\ndescription = "hybrid-display"\ndef force(value):\n    return value\n'
        self.assertEqual(wiring_violations('prototype/hybrid-focus/example.py', source, 'focus'), [])
        for source in ('import hybrid_display.cli\n', 'from hybrid_display import cli\n',
                       'import importlib\nimportlib.import_module("hybrid_display.cli")\n'):
            self.assertTrue(wiring_violations('prototype/hybrid-focus/example.py', source, 'focus'))


    def test_javascript_comments_names_and_descriptions_do_not_wire_decky(self):
        source = '// import "hybrid_display";\n/* hybrid-display */\nconst name = "hybrid-display";\nconst description = "prototype/hybrid-display";\n'
        self.assertEqual(wiring_violations('prototype/hybrid-focus/decky/index.tsx', source, 'focus'), [])
        for source in ('import cli from "hybrid_display";',
                       'const runner = require("hybrid_display");',
                       'api.call_plugin_method("hybrid_display_start", {});'):
            self.assertTrue(wiring_violations('prototype/hybrid-focus/decky/index.tsx', source, 'focus'))


    def test_hardware_contract_ignores_force_prose_but_rejects_control_paths(self):
        harmless = '"""force and /sys/class/drm are forbidden runtime operations."""\ndef force(value):\n    return value\n'
        self.assertEqual(product_violations('example.py', harmless), [])
        for source in ('target = "/sys/class/drm/card0-DP-1/force"\n',
                       'target = "/sys/kernel/debug/dri/0"\n',
                       'argv = ["kscreen-doctor", "output.1.enable"]\n',
                       'env = {"WLR_DRM_DEVICES": "/dev/dri/card0"}\n',
                       'adapter.trigger_hotplug()\n', 'drm.create_lease()\n'):
            self.assertTrue(product_violations('example.py', source), source)


    def test_display_cannot_import_focus_or_share_inputplumber_profiles(self):
        for source in ('from bazzite_hybrid_focus import client\n',
                       'profile = "prototype/hybrid-focus/inputplumber/profile.yaml"\n',
                       'import inputplumber\n', 'plugin = "decky_plugin"\n'):
            self.assertTrue(product_violations('display.py', source), source)
        self.assertEqual(product_violations('display.py',
                         '"""No hybrid-focus, InputPlumber or Decky integration."""\n'), [])


    def test_launcher_files_packaging_and_executable_bits_are_rejected(self):
        for path in ('bin', 'bin/hybrid-display-run', 'install-user.sh', 'uninstall-user.sh',
                     'systemd/display.service', 'display.desktop', 'pyproject.toml',
                     'setup.py', 'setup.cfg', 'package.json'):
            errors = launcher_violations([path])
            self.assertTrue(errors, path)
            self.assertIn('no-launcher', errors[0])
        self.assertTrue(launcher_violations(['src/hybrid_display/cli.py'], ['src/hybrid_display/cli.py']))
        self.assertEqual(launcher_violations(['README.md', 'src/hybrid_display/cli.py']), [])


    def test_workflow_data_keys_and_comments_are_distinguished(self):
        for field in ('uses', 'with', 'env', 'services', 'container', 'defaults', 'working-directory', 'future-execution-field'):
            source = field + ':\n  name: prototype/hybrid-display\n'
            self.assertTrue(wiring_violations('.github/workflows/example.yml', source), field)
        for source in ('name: hybrid-display\ndescription: prototype/hybrid-display\n',
                       'run: echo normal # hybrid-display is not integrated\n',
                       'run: |\n  echo normal # prototype/hybrid-display\n',
                       'env:\n  DOCS: docs/hybrid-display.md\n'):
            self.assertEqual(wiring_violations('.github/workflows/example.yml', source), [])
        self.assertTrue(wiring_violations('.github/workflows/example.yml',
                                         'run: exec helper "#prototype/hybrid-display"\n'))

    def test_shell_and_just_comments_keep_quoted_execution_arguments(self):
        for path in ('build_files/build.sh', 'Justfile', 'system_files/etc/gamescope-session-plus/sessions.d/steam'):
            self.assertEqual(wiring_violations(path, '# exec hybrid-display-run\necho normal # hybrid-display\n'), [])
            self.assertTrue(wiring_violations(path, 'exec helper "#prototype/hybrid-display"\n'))
            self.assertEqual(wiring_violations(path, 'echo docs/hybrid-display.md\n'), [])


    def test_preflight_focus_conflict_facts_are_not_focus_integration(self):
        source = 'codes = ("decky_active", "focus_integration_active")\n'
        self.assertEqual(product_violations('example.py', source), [])
        self.assertTrue(product_violations('example.py', 'import decky_active\n'))
