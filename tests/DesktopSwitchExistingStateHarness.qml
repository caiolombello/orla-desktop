import QtQuick
import "../package/contents/ui" as Orla
Item {
    id: fixture
    property var sourceSnapshot: ({outputName:"Fixture",activity:{status:"unavailable",currentId:"",ids:[],names:[]},
        desktop:{status:"ready",currentId:"11111111-1111-4111-8111-111111111111",ids:["11111111-1111-4111-8111-111111111111","22222222-2222-4222-8222-222222222222"],names:["Primeira","Segunda"]}})
    Orla.ContextState { id: contexts; sourceSnapshot: fixture.sourceSnapshot }
    QtObject {
        id: transport
        property var queue: []
        property var messages: []
        function asyncCall(message,resolve,reject) {messages=messages.concat([message]);queue=queue.concat([{resolve:resolve,reject:reject}]);}
        function reply(value) {const callback=queue[0];queue=queue.slice(1);callback.resolve({value:value});}
    }
    Orla.KdeDesktopSwitchBackend {id: backend;objectName:"backend";contexts:contexts;transport:transport;active:true}
    Orla.DesktopSwitchState {id: state;objectName:"state";contexts:null;backend:backend;active:false;confirmationTimeoutMs:10000}
    function reply(value) { transport.reply(value); }
    function attachState() {state.contexts=contexts;state.active=true;}
    property int requestRevision: -1
    function request() {requestRevision=state.desktopRevision; return state.requestDesktopSwitch("22222222-2222-4222-8222-222222222222",state.desktopRevision); }
    function observedSource() {sourceSnapshot={outputName:"Fixture",activity:{status:"unavailable",currentId:"",ids:[],names:[]},desktop:{status:"ready",currentId:"22222222-2222-4222-8222-222222222222",ids:["11111111-1111-4111-8111-111111111111","22222222-2222-4222-8222-222222222222"],names:["Primeira","Segunda"]}};}
    function evidence() {return JSON.stringify({status:state.status,pending:state.pending,current:state.currentId,revision:state.desktopRevision,requestRevision:requestRevision,rawCurrent:contexts.snapshot.desktop.id,sets:transport.messages.filter(m=>m.member==="Set").length});}
}
