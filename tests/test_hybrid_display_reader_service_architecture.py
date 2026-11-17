"""Repository-only guards for the reviewed reader-service design.

These tests protect explicit normative clauses and structured values, not natural
language semantics or native enforcement. No service, IPC or sandbox is exercised.
Mutations are detached strings: repository documents are never changed by tests.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADR = 'docs/superpowers/specs/2026-11-17-hybrid-display-reader-service-adr.md'
SECURITY = 'docs/superpowers/specs/2026-11-17-hybrid-display-reader-service-security.md'
PLAN = 'docs/superpowers/plans/2026-11-17-hybrid-display-reader-service-implementation.md'
DOCUMENTS = (ADR, SECURITY, PLAN)


def normalized(text):
    return re.sub(r'\s+', ' ', text.replace('`', '').replace('**', '')).strip()


def section(text, title):
    match = re.search(r'(?m)^(#{2,3}) ' + re.escape(title) + r'\s*$', text)
    if match is None:
        return ''
    rest = text[match.end():]
    stop = re.search(r'(?m)^#{1,' + str(len(match[1])) + r'} ', rest)
    return rest[:stop.start()] if stop else rest


def rows(text):
    return [tuple(normalized(cell) for cell in line.strip().strip('|').split('|'))
            for line in text.splitlines() if line.startswith('|')]


def contract_issues(documents):
    """Closed section/key guards; no claim to parse arbitrary prose or negation."""
    missing = [name for name in DOCUMENTS if name not in documents]
    if missing:
        return {'inventory': tuple('missing:' + name for name in missing)}
    issues = {}

    def require(group, text, *patterns):
        for pattern in patterns:
            if re.search(pattern, normalized(text)) is None:
                issues.setdefault(group, []).append(pattern)

    def table_value(group, table, key, value):
        matches = [row[1] for row in rows(table) if len(row) >= 2 and row[0] == key]
        if matches != [value]:
            issues.setdefault(group, []).append('table:' + key)

    adr, security, plan = (documents[name] for name in DOCUMENTS)
    decision = section(adr, 'Anlass und Entscheidung')
    identity = section(adr, 'Feste Identitäten und Protokoll')
    migration = section(adr, 'Eng begrenzte Änderung der bisherigen Verträge')
    gates = section(adr, 'Folgen, Alternativen und offene Freigabegates')
    peer = section(security, 'Prozess, Socket und Identitätsgrenze')
    resources = section(security, 'Ressourcen und zeitliche Grenzen')
    sandbox = section(security, 'Sandboxmatrix: statische Prüfung und spätere Abnahme')
    protocol = section(security, 'Protokoll v1: vollständiger begrenzter Austausch')
    safety = section(security, 'Safety-Migration: einzeln, testgetrieben, keine heutige Lockerung')
    implementation_gate = section(plan, 'Aufgabe1: Umsetzungsfähigkeit als explizites Gate')

    require('service', decision, r'Genau ein fest installiertes natives Readerprogramm',
            r'einen fest benannten systemd-User-Service', r'Hauptprozess startet keinen Befehl:',
            r'Keine Shell, argv, Helperwahl,', r'generische subprocess-\s*API, Templates, Workerpools')
    # Keyed bullets, including multiplicity, catch extra named services/sockets.
    for label, value in (('Service', 'hybrid-display-reader-v1.service'),
                         ('Socketunit', 'hybrid-display-reader-v1.socket, ausschließlich Accept=no')):
        matches = re.findall(r'(?m)^-[ \t]+' + label + r':[ \t]+([^\n]+)', identity)
        if [normalized(item).rstrip('.') for item in matches] != [value]:
            issues.setdefault('service', []).append('identity:' + label)
    require('service', identity, r'Ein einziges ExecStart-Programm ohne Argumente')
    require('protocol', identity,
            r'Clientsocket: %t/hybrid-display-reader-v1\.sock,', r'eigene UID, Modus 0600',
            r'Pro Verbindung ein Request CAPTURE_IPC, Protokollversion 1, längenpräfixiert,',
            r'maximal 4096 Requestbytes und 262144 Responsebytes einschließlich Header',
            r'Keine freien Pfade, Methoden, Busadressen, Kommandos, Profil-/Gateoverrideflags')
    require('protocol', protocol, r'AF_UNIX SOCK_STREAM\. Header genau16 Bytes',
            r'Magic4=HDR1, Version u16=1, Typ u16, Bodylänge u32, Request-ID u32=1',
            r'Länge vor Bodyallokation', r'Gesamtframe maximal262144 B; Request maximal4096 B',
            r'Einziger Requesttyp 1=CAPTURE_IPC', r'Datenlänge muss exakt1\+4\*C sein',
            r'Keine andere Quelle wird durch Requestparameter wählbar',
            r'keine Gate-/Profil-/Timeout-/Größenoverrides', r'Keine Kompression, Pickle, generischen RPCs',
            r'Reader verlangt EOF unter derselben Requestfrist, bevor er Quellen befragt',
            r'SCM_RIGHTS wird auf dem Clientsocket abgelehnt',
            r'tatsächlich empfangene FDs werden geschlossen', r'Ancillary-Truncation ist Fehler')
    require('peer_deadline', peer, r'prüft SO_PEERCRED:', r'UID exakt eigene unprivilegierte UID',
            r'nicht mit einer PID aus dem Request', r'SSH, manager, remote, unbekannt oder',
            r'blockieren vor KScreen', r'jeweils dieselbe bestätigte Session besitzen',
            r'wird niemals als nachgewiesene Reader-Binary')
    for key, value in (
        ('Hauptprozessdeadline', '5s ab vor connect'),
        ('Reader-Gesamtdeadline', '4s ab Prozesseintritt, beide Captures'),
        ('Header / kompletter Request', '100ms / 250ms ab accept'),
        ('Responseausgabe', '250ms, innerhalb 4s'),
        ('MemoryMax / MemoryHigh / MemorySwapMax', '64M / 48M / 0'),
        ('TasksMax', '1'), ('CPUQuota / CPUQuotaPeriodSec', '25% / 100ms'),
    ):
        table_value('peer_deadline', resources, key, value)
    require('peer_deadline', protocol, r'Ein Streamfragment verlängert nie eine Deadline',
            r'Commitpunkt ist erst der vollständig validierte Frame plus EOF innerhalb dieser Frist',
            r'kann dasselbe EOF wie ein normaler Exit erzeugen',
            r'Hauptprozess reconnectet nicht nach Disconnect oder Serviceabsturz')
    require('privacy', protocol,
            r'Response 0xffff=BLOCKED: Body genau ein u16', r'keine Detailfelder oder Teilergebnisse',
            r'kein Adapter-/Snapshot-/Preflighterfolg', r'keine Roh-EDID in Logs/Diagnosen',
            r'Keine neuen dynamischen Codes, Exceptiontexte, Hashes, Pfade, Personen-/Sessiondaten',
            r'Kein Responsebody vor vollständiger Schema-/Grenzprüfung als Facts sichtbar')
    expected_codes = dict(enumerate((
        'input_invalid', 'source_not_allowed', 'source_unavailable', 'source_denied',
        'source_limit', 'source_timeout', 'source_type_invalid', 'ipc_invalid', 'ipc_limit',
        'owner_missing', 'owner_invalid', 'session_unverified', 'inventory_changed',
        'kscreen_profile_unverified', 'client_inventory_unverified', 'reader_deadline_unverified',
        'reader_failed', 'edid_invalid', 'kscreen_unavailable', 'kscreen_schema_invalid'), 1))
    code_rows = []
    for row in rows(protocol):
        if len(row) == 4 and row[0].isdigit():
            code_rows.extend(((int(row[0]), row[1]), (int(row[2]), row[3])))
    if sorted(code_rows) != sorted(expected_codes.items()):
        issues.setdefault('privacy', []).append('closed-wire-code-table')
    require('blockers', safety, r'Offen vor Umsetzung mit echten Units: konkrete Native-Runtime',
            r'AUTH-/FD-Eignung', r'tatsächlicher Usernamespace-/Cgroup-/Seccompvollzug',
            r'Same-UID-/Busmethoden-Restbedrohungsmodell',
            r'Bis dahin keine Installation, automatische Aktivierung oder Livefunktion')
    require('blockers', plan, r'Build-/Loader-/Packagingformat',
            r'erst nach Aufgabe1 in einem konkret genehmigten Scope')
    require('blockers', implementation_gate, r'Kein Default-libdbus-Erfolg annehmen',
            r'Same-UID- und mutierende Busmethoden-Restgrenze explizit akzeptieren lassen',
            r'Ohne Ergebnis hier nur reine Aufgaben2/3 erlaubt')
    require('blockers', sandbox, r'Unwirksame, unbekannte oder nur still ignorierte Einstellungen',
            r'Nichtfreigabe', r'keine Abschwächung für einen grünen Test')
    sandbox_conditions = {
        'ProtectHome=true': (r'Verdeckt auch /run/user', r'nicht als unverändert kompatibel behaupten'),
        'PrivateTmp=true': (r'zusätzlich /tmp und /var/tmp explizit read-only', r'keine Ausnahmen'),
        'PrivateNetwork=true': (r'Eigener tatsächlich wirksamer Netzwerknamespace',
                                r'Ohne wirksame Isolation keine Freigabe'),
        'RestrictAddressFamilies=AF_UNIX': (r'Keine AF_INET/AF_INET6/AF_NETLINK',
                                          r'keine geerbten fremden Socketfamilien'),
        'MemoryDenyWriteExecute=true': (r'bei Konflikt Runtime verwerfen', r'nicht Option entfernen'),
        'SystemCallArchitectures=native': (r'Keine32-Bit-/Compat-ABI',),
        'SystemCallFilter': (r'ausschließen; exakte aufgelöste native Allowlist vor Packaging einfrieren',),
        'NoNewPrivileges=true; CapabilityBoundingSet/ AmbientCapabilities leer':
            (r'Keine Privilegiengewinnung, kein sudo/root',),
        'RestrictSUIDSGID=true; LockPersonality=true': (r'Keine SUID-/SGID-Erzeugung',),
    }
    for setting, conditions in sandbox_conditions.items():
        matches = [row[1] for row in rows(sandbox) if len(row) >= 2 and row[0] == setting]
        if len(matches) != 1:
            issues.setdefault('blockers', []).append('sandbox:' + setting)
        else:
            require('blockers', matches[0], *conditions)
    expected_gates = {'kscreen_profile': 'BLOCKED', 'ipc_transport': 'UNKNOWN',
                      'drm_read_deadlines': 'UNKNOWN', 'client_completeness': 'BLOCKED'}
    found = re.findall(r'\b(kscreen_profile|ipc_transport|drm_read_deadlines|client_completeness) '
                       r'(BLOCKED|UNKNOWN|SELECTED|SUPPORTED)', normalized(gates))
    if len(found) != 4 or dict(found) != expected_gates:
        issues.setdefault('gates', []).append('unchanged-four-gates')
    require('no_integration', adr, r'Ausführung und Deployment bleiben gesperrt')
    require('no_integration', decision, r'Heute werden weder Unit noch Programm, Installer oder Aktivierung erstellt')
    require('no_integration', gates, r'kein vollständiger Hostsnapshot, keine Startfreigabe',
            r'kein Nachweis realer KWin-, Display- oder Hardwarefunktion',
            r'Keine heutige Implementierungs-, Installations-, Build-, Live-, Git- oder Workflowfreigabe')
    require('general_bans', migration, r'Unverändert bleiben: Quellen-/Methoden-Allowlist,',
            r'Nichtautostart von D-Bus-\s*Diensten', r'kein subprocess im Hauptprozess',
            r'keine Produkt-/Releaseintegration', r'keine Cookiequelle und kein FD-Handshake',
            r'nicht still aufgehoben', r'Der Hauptprozess sendet keine Signale',
            r'Keine automatische Restart-/Reconnect-/Recovery-/Serviceaktivierungs-Schleife')
    require('general_bans', safety, r'reject_command und seine Null-Spawn-Tests bleiben vollständig unverändert',
            r'Globale Release-/Payload-/Session-/Focus-Scanner sowie Classifier bleiben unverändert',
            r'Kein blanket-ignore', r'AST-Verbote für kill/spawn/exec bleiben im Hauptprozess bestehen')
    return issues


class ReaderServiceArchitectureTests(unittest.TestCase):
    def documents(self):
        result = {}
        for name in DOCUMENTS:
            path = ROOT / name
            # Only repository files, never a symlink target outside the repository.
            self.assertTrue(path.resolve().is_relative_to(ROOT), 'outside repository: ' + name)
            self.assertFalse(path.is_symlink(), 'symlink document: ' + name)
            self.assertTrue(path.is_file(), 'missing architecture document: ' + name)
            try:
                result[name] = path.read_text(encoding='utf-8')
            except UnicodeError:
                self.fail('architecture document must be UTF-8: ' + name)
        return result

    def assert_contract(self, group):
        self.assertNotIn(group, contract_issues(self.documents()))

    def test_exact_architecture_file_set(self):
        documents = self.documents()
        found = set()
        for directory in ('specs', 'plans'):
            base = ROOT / 'docs/superpowers' / directory
            self.assertTrue(base.resolve().is_relative_to(ROOT))
            found.update(str(path.relative_to(ROOT)) for path in
                         base.glob('*hybrid-display-reader-service*.md'))
        self.assertEqual(found, set(DOCUMENTS))
        self.assertEqual(set(documents), set(DOCUMENTS))

    def test_only_one_named_service_without_general_execution(self):
        self.assert_contract('service')

    def test_fixed_versioned_unix_protocol_has_size_limits(self):
        self.assert_contract('protocol')

    def test_peer_absolute_deadlines_and_atomic_commit_are_required(self):
        self.assert_contract('peer_deadline')

    def test_failure_responses_are_private_atomic_and_closed(self):
        self.assert_contract('privacy')

    def test_unproven_runtime_auth_sandbox_packaging_and_uid_block(self):
        self.assert_contract('blockers')

    def test_four_gates_remain_fail_closed(self):
        self.assert_contract('gates')

    def test_no_product_installation_or_real_function_is_claimed(self):
        self.assert_contract('no_integration')

    def test_general_command_source_and_release_bans_survive(self):
        self.assert_contract('general_bans')

    def assert_weakening_rejected(self, documents):
        mutations = (
            (ADR, 'Service: `hybrid-display-reader-v1.service`', 'Service: `arbitrary.service`', 'service'),
            (ADR, 'Keine Shell, argv, Helperwahl,', 'Shell, argv, Helperwahl erlaubt,', 'service'),
            (SECURITY, 'Ohne wirksame Isolation keine Freigabe',
             'Ohne wirksame Isolation trotzdem Freigabe', 'blockers'),
            (SECURITY, 'bei Konflikt Runtime verwerfen, nicht Option entfernen',
             'bei Konflikt Option entfernen und fortfahren', 'blockers'),
            (SECURITY, 'zusätzlich /tmp und /var/tmp explizit read-only, leer, keine Ausnahmen',
             'tmp darf beschreibbar bleiben', 'blockers'),
            (SECURITY, 'SCM_RIGHTS wird auf dem Clientsocket abgelehnt',
             'SCM_RIGHTS wird auf dem Clientsocket akzeptiert', 'protocol'),
            (SECURITY, 'tatsächlich empfangene FDs\nwerden geschlossen',
             'tatsächlich empfangene FDs dürfen offen bleiben', 'protocol'),
            (SECURITY, 'Ancillary-Truncation ist Fehler',
             'Ancillary-Truncation wird ignoriert', 'protocol'),
            (SECURITY, 'Reader verlangt EOF\nunter derselben Requestfrist, bevor er Quellen befragt',
             'Reader befragt Quellen ohne EOF', 'protocol'),
            (ADR, 'Der Hauptprozess sendet keine Signale',
             'Der Hauptprozess darf beliebige Signale senden', 'general_bans'),
            (ADR, 'Keine automatische Restart-/Reconnect-/Recovery-/Serviceaktivierungs-Schleife',
             'Automatische Restart-/Reconnect-/Recovery-/Serviceaktivierungs-Schleife erlaubt', 'general_bans'),
            (ADR, 'Protokollversion 1', 'Protokollversion 2', 'protocol'),
            (SECURITY, 'Gesamtframe maximal262144 B', 'Gesamtframe maximal999999999 B', 'protocol'),
            (SECURITY, '| Hauptprozessdeadline | 5s ab vor connect |',
             '| Hauptprozessdeadline | unendlich |', 'peer_deadline'),
            (SECURITY, 'nicht\nmit einer PID aus dem Request',
             'auch\nmit einer PID aus dem Request', 'peer_deadline'),
            (SECURITY, 'keine Detailfelder oder Teilergebnisse',
             'Detailfelder und Teilergebnisse erlaubt', 'privacy'),
            (SECURITY, 'kscreen_schema_invalid |', 'input_invalid |', 'privacy'),
            (SECURITY, 'Bis dahin keine Installation, automatische Aktivierung oder Livefunktion',
             'Bis dahin Installation und automatische Aktivierung erlaubt', 'blockers'),
            (PLAN, 'Ohne Ergebnis hier nur reine Aufgaben2/3 erlaubt',
             'Ohne Ergebnis sind auch native Aufgaben erlaubt', 'blockers'),
            (ADR, 'ipc_transport **UNKNOWN**', 'ipc_transport **SELECTED**', 'gates'),
            (ADR, 'kein Nachweis realer KWin-, Display- oder Hardwarefunktion',
             'Nachweis realer KWin-, Display- oder Hardwarefunktion', 'no_integration'),
            (ADR, 'keine Produkt-/Releaseintegration', 'Produkt-/Releaseintegration erlaubt', 'general_bans'),
            (SECURITY, 'Globale Release-/Payload-/Session-/Focus-Scanner sowie Classifier bleiben\n   unverändert',
             'Globale Release-/Payload-/Session-/Focus-Scanner sowie Classifier werden\n   gelockert', 'general_bans'),
        )
        for name, before, after, group in mutations:
            with self.subTest(group=group, clause=before):
                pattern = r'\s+'.join(re.escape(part) for part in before.split())
                matches = list(re.finditer(pattern, documents[name]))
                self.assertEqual(len(matches), 1, 'mutation must reach one normative clause')
                match = matches[0]
                changed = dict(documents)
                changed[name] = documents[name][:match.start()] + after + documents[name][match.end():]
                self.assertIn(group, contract_issues(changed))

    def test_guard_detects_weakened_normative_contracts_in_memory(self):
        self.assert_weakening_rejected(self.documents())

    def test_guard_accepts_editorial_whitespace_without_contract_changes(self):
        documents = self.documents()
        changed = {name: re.sub(r'(?m)^(?!#|\|)([^\n]+)$',
                               lambda match: match[0].replace(' ', '  '), text)
                   for name, text in documents.items()}
        self.assertEqual(contract_issues(changed), {})
        self.assert_weakening_rejected(changed)
