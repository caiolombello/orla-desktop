import QtQuick
import "../package/contents/ui" as Orla
Item {
 id:root
 property var sourceSnapshot:({outputName:"Fixture",activity:{status:"unavailable",currentId:"",ids:[],names:[]},desktop:{status:"ready",currentId:"one",ids:["one","two"],names:["Uma","Outra"]}})
 property int replies:0
 property int observations:0
 property int failures:0
 property bool guardAllowed:true
 property bool hideOnFinalDispatch:false
 property bool hideOnObserve:false
 property int dispatchChecks:0
 property string observedCurrent:""
 Orla.ContextState {id:contexts;sourceSnapshot:root.sourceSnapshot}
 QtObject {
  id:transport;objectName:"transport"
  property var messages:[]
  property var queue:[]
  function asyncCall(message,resolve,reject) { messages=messages.concat([message]); queue=queue.concat([{resolve:resolve,reject:reject}]); }
  function reply(value) { const next=queue[0];queue=queue.slice(1);next.resolve({value:value}); }
  function reject() {const next=queue[0];queue=queue.slice(1);next.reject();}
 }
 Orla.KdeDesktopSwitchBackend {
  id:backend;objectName:"adapter";contexts:contexts;transport:transport;active:true
  onSetReplied: root.replies++
  onReadback: (requestId,currentId,owner) => {root.observations++;root.observedCurrent=currentId;}
  onFailed: root.failures++
 }
 property var commandState: null
 Component {
  id:commandFactory
  Orla.DesktopSwitchState {objectName:"compositionState";confirmationTimeoutMs:10000}
 }
 function attachState() {commandState=commandFactory.createObject(root,{contexts:contexts,backend:backend,active:true});}
 function attachStateFirst() {
  backend.active=false;
  backend.contexts=null;
  transport.queue=[];
  attachState();
  backend.contexts=contexts;
  backend.active=true;
 }
 function requestState() {return commandState.requestDesktopSwitch("two",commandState.desktopRevision);}
 function modelCurrent(id) {sourceSnapshot={outputName:"Fixture",activity:sourceSnapshot.activity,desktop:{status:"ready",currentId:id,ids:["one","two"],names:["Uma","Outra"]}};}
 function request() {return backend.requestDesktopSwitch("two",41,phase=>{if(phase==="dispatch") {root.dispatchChecks++;if(root.hideOnFinalDispatch && root.dispatchChecks>1) backend.active=false;}if(phase==="observe" && root.hideOnObserve) backend.active=false;return root.guardAllowed;});}
}
