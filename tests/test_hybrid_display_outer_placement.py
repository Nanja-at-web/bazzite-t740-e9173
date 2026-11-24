"""Execute the actual placement script against JS-only KWin doubles."""
import json
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'prototype/hybrid-display/session/kwin/outer-placement/contents/code/main.js'


def javascript(program):
    # No graphical client/compositor is created: only a language engine.
    node = shutil.which('node')
    if node:
        result = subprocess.run([node], input=program + '\nprocess.stdout.write(JSON.stringify(answer));',
                                text=True, capture_output=True, timeout=5, check=True)
        return json.loads(result.stdout)
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtQml import QJSEngine
    app = QCoreApplication.instance() or QCoreApplication([])
    engine = QJSEngine()
    result = engine.evaluate(program + '\nJSON.stringify(answer);')
    if result.isError():
        raise AssertionError(result.toString())
    answer = json.loads(result.toString())
    del engine
    return answer


HARNESS = r'''
var notes = [], writes = [], added = function () {};
var console = {warn: function(s) {notes.push(s);}};
function readConfig(key, fallback) {
    return ({GamingOutput:'DP-2', SideOutput:'DP-1', Receipt:'fixture'})[key] || fallback;
}
function QTimer() {this.timeout={connect:function(fn){}}; this.start=function(){}; this.stop=function(){};}
var screens=[{name:'DP-1',geometry:{x:0,y:0,width:1920,height:1080}},
             {name:'DP-2',geometry:{x:1920,y:0,width:1920,height:1080}}];
var windows=[];
var workspace={screens:screens, windowList:function(){return windows;},
    windowAdded:{connect:function(fn){added=fn;}},
    screensChanged:{connect:function(fn){}},
    sendClientToScreen:function(w,o){writes.push('move'); if (!w.refuseMove) w.output=o;}};
function win() {
    var w={normalWindow:true,resourceClass:'gamescope',resourceName:'gamescope',
      desktopFileName:'gamescope',pid:71,output:screens[0],closeCount:0,
      closeWindow:function(){this.closeCount++;}, refuseMove:false, refuseFull:false,
      onClosed:function(){},closed:{connect:function(fn){w.onClosed=fn;}},
      closedSignal:{connect:function(fn){}}, fullScreenChanged:{connect:function(fn){}},
      outputChanged:{connect:function(fn){}}, windowClosed:{connect:function(fn){}}};
    Object.defineProperty(w,'fullScreen',{get:function(){return this.fs===true;},
      set:function(v){writes.push('fullscreen');this.fs=this.refuseFull?false:v;}});
    return w;
}
'''


class PlacementTests(unittest.TestCase):
    def test_unavailable_executable_hint_requires_both_exact_app_id_fields(self):
        answer = self.case(after="var w=win();w.resourceName='';added(w);var answer={name:w.output.name,fs:w.fullScreen,closed:w.closeCount};")
        self.assertEqual(answer, {'name': 'DP-2', 'fs': True, 'closed': 0})

    def test_overlapping_outputs_block_private_script_activation(self):
        answer = self.case('screens[1].geometry.x=0;', 'var answer=notes;')
        self.assertNotIn('HYBRID_OUTER_READY_V1:fixture', answer)
        self.assertIn('HYBRID_OUTER_FAIL_V1:fixture', answer)

    def case(self, before='', after=''):
        return javascript(HARNESS + before + SCRIPT.read_text() + after)

    def test_ready_requires_two_exact_named_outputs_and_no_windows(self):
        answer = self.case(after='var answer=notes;')
        self.assertIn('HYBRID_OUTER_READY_V1:fixture', answer)

    def test_missing_duplicate_or_extra_target_blocks_readiness(self):
        for edit in ("screens.pop();", "screens[1].name='DP-1';", "screens.push(screens[0]);",
                     "screens[1].geometry.width=0;", "windows.push(win());"):
            answer = self.case(edit, 'var answer=notes;')
            self.assertNotIn('HYBRID_OUTER_READY_V1:fixture', answer)
            self.assertIn('HYBRID_OUTER_FAIL_V1:fixture', answer)

    def test_moves_by_name_then_fullscreen_and_checks(self):
        answer = self.case(after="var w=win(); added(w); var answer={writes:writes,name:w.output.name,fs:w.fullScreen,closed:w.closeCount};")
        self.assertEqual(answer, {'writes': ['move', 'fullscreen'], 'name': 'DP-2', 'fs': True, 'closed': 0})

    def test_ineffective_output_assignment_closes_without_fullscreen(self):
        answer = self.case(after="var w=win();w.refuseMove=true;added(w);var answer={writes:writes,closed:w.closeCount};")
        self.assertEqual(answer, {'writes': ['move'], 'closed': 1})

    def test_fullscreen_refusal_closes(self):
        answer = self.case(after="var w=win();w.refuseFull=true;added(w);var answer=w.closeCount;")
        self.assertEqual(answer, 1)

    def test_similar_or_foreign_identity_never_changes_foreign_window(self):
        for field in ('resourceClass', 'resourceName', 'desktopFileName'):
            answer = self.case(after=f"var w=win();w.{field}='prefix-gamescope';added(w);var answer={{writes:writes,closed:w.closeCount,notes:notes}};")
            self.assertEqual(answer['writes'], [])
            self.assertEqual(answer['closed'], 0)
            self.assertIn('HYBRID_OUTER_FAIL_V1:fixture', answer['notes'])

    def test_second_gamescope_aborts_first_not_foreign_windows(self):
        answer = self.case(after="var a=win(),b=win();added(a);added(b);var answer={first:a.closeCount,second:b.closeCount,notes:notes};")
        self.assertEqual(answer['first'], 1)
        self.assertEqual(answer['second'], 0)
        self.assertIn('HYBRID_OUTER_FAIL_V1:fixture', answer['notes'])

    def test_later_side_application_is_untouched(self):
        answer = self.case(after="var a=win();added(a);var b=win();b.resourceClass='side';b.desktopFileName='side';added(b);var answer={writes:writes,closed:b.closeCount};")
        self.assertEqual(answer, {'writes': ['move', 'fullscreen'], 'closed': 0})

    def test_closed_gamescope_window_requests_session_abort_without_reclosing(self):
        answer = self.case(after="var w=win();added(w);w.onClosed();var answer={notes:notes,closed:w.closeCount};")
        self.assertIn('HYBRID_OUTER_FAIL_V1:fixture', answer['notes'])
        self.assertEqual(answer['closed'], 0)
