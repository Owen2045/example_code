
// 需要搭配 jquery.blockUI.js 使用
function openYH(){
    $.blockUI({
        message: "<img src='/static/users/img/spinner.gif' style='width:100%' >", 
        //borderWidth:'0px' 和透明背景
        css: { borderWidth: '0px', backgroundColor: 'transparent', position:'absolute',top:'10vh'},
    });
}

function closeYH(){
    $.unblockUI();
}