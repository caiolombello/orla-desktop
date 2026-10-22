import QtQuick
import "../package/contents/code/Style.js" as Style
import "../package/contents/ui" as Orla
Item {
 id:harness
 width:420; height:260
 property bool fixtureDark:false
 readonly property var fixtureScheme:Style.scheme(fixtureDark ? "dark" : "light")
 property var sourceSnapshot:({outputName:"Fixture",activity:{status:"ready",currentId:"activity",ids:["activity"],names:["Activity"]},desktop:{status:"ready",currentId:"one",ids:["one","two","three"],names:["Área","Área","Terceira"]}})
 property string profilesJSON:"preserved-profile-bytes"
 property string contextsJSON:"future-preserved-context-bytes"
 property string activeProfileId:"work"
 property double pomodoroDeadline:1234567890000
 property bool previewDirty:true
 function source(current,ids,names) { sourceSnapshot={outputName:"Fixture",activity:sourceSnapshot.activity,desktop:{status:"ready",currentId:current,ids:ids||["one","two","three"],names:names||["Área","Área","Terceira"]}}; }
 Orla.ContextState {id:contexts;sourceSnapshot:harness.sourceSnapshot}
 QtObject {
  id:backend;objectName:"backend"
  property bool available:true
  property string status:available?"ready":"unavailable"
  property int calls:0
  property int cancellations:0
  property int lastId:-1
  property string target:""
  property var guard:null
  property bool replaceDuringRequest:false
  property bool reenterDuringCancel:false
  property bool reentered:false
  signal setReplied(int requestId,string owner)
  signal readback(int requestId,string currentId,string owner)
  signal failed(int requestId)
  function requestDesktopSwitch(targetId,requestId,validate) {calls++;target=targetId;lastId=requestId;guard=validate;if(replaceDuringRequest) state.backend=replacement;return true;}
  function cancel(requestId) {cancellations++;if(reenterDuringCancel) reentered=state.requestDesktopSwitch("two",state.desktopRevision);}
  function reply() {setReplied(lastId,":1.44");}
  function observed(id) {readback(lastId,id,":1.44");}
 }
 QtObject {
  id:replacement;objectName:"replacement"
  property bool available:true
  property int calls:0
  property int cancellations:0
  signal setReplied(int requestId,string owner)
  signal readback(int requestId,string currentId,string owner)
  signal failed(int requestId)
  function requestDesktopSwitch(targetId,requestId,validate) {calls++;return true;}
  function cancel(requestId) {cancellations++;}
 }
 Orla.DesktopSwitchState {id:state;objectName:"state";contexts:contexts;backend:backend;active:true;confirmationTimeoutMs:10000}
 Orla.DesktopSwitchControls {
  anchors.fill:parent;command:state
  palette.window:harness.fixtureScheme.surface
  palette.base:harness.fixtureScheme.raised
  palette.text:harness.fixtureScheme.text
  palette.windowText:harness.fixtureScheme.text
  palette.buttonText:harness.fixtureScheme.text
  palette.button:harness.fixtureScheme.surface
  palette.highlight:harness.fixtureScheme.accent
  palette.mid:harness.fixtureScheme.borderStrong
 }

 function request(id) {return state.requestDesktopSwitch(id,state.desktopRevision);}
}
