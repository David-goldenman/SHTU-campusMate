// Keep a zoom anchor at the same screen position, including at the zoom limits.
export function zoomView(view, projection, factor, anchor={x:view.x+view.w/2,y:view.y+view.h/2}) {
  const w=Math.min(projection.width*1.2,Math.max(projection.width/5,view.w*factor));
  const h=w*projection.height/projection.width;
  return {x:anchor.x-(anchor.x-view.x)*w/view.w,y:anchor.y-(anchor.y-view.y)*h/view.h,w,h};
}

export function bindMapGestures(svg,{signal,getView,setView,onTap,onZoom}) {
  let drag;
  const on=(name,handler,options={})=>svg.addEventListener(name,handler,{signal,...options});
  const localPoint=event=>{
    const matrix=svg.getScreenCTM();if(!matrix)return;
    const point=svg.createSVGPoint();point.x=event.clientX;point.y=event.clientY;
    return point.matrixTransform(matrix.inverse());
  };
  function cancel() {
    const previous=drag;drag=undefined;
    svg.classList.remove('is-dragging');
    if(previous&&svg.hasPointerCapture(previous.id))svg.releasePointerCapture(previous.id);
  }
  function pan(event) {
    const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
    if(Math.hypot(dx,dy)>4)drag.moved=true;
    // A click may jitter. Do not pan or replace its label before it becomes a drag.
    if(!drag.moved)return;
    svg.classList.add('is-dragging');
    const rect=svg.getBoundingClientRect(),scale=Math.max(drag.view.w/rect.width,drag.view.h/rect.height);
    setView({...drag.view,x:drag.view.x-dx*scale,y:drag.view.y-dy*scale});
  }
  on('pointerdown',event=>{
    const view=getView();if(!view||drag||event.button!==0||event.isPrimary===false)return;
    event.preventDefault();svg.focus({preventScroll:true});
    drag={id:event.pointerId,x:event.clientX,y:event.clientY,view:{...view},moved:false,
      building:event.target.closest('[data-building]')?.dataset.building,
      road:event.target.closest('[data-maint-road]')?.dataset.maintRoad};
    svg.setPointerCapture(event.pointerId);
  });
  on('pointermove',event=>{
    if(drag?.id!==event.pointerId)return;
    if(event.pointerType==='mouse'&&(event.buttons&1)===0){cancel();return;}
    pan(event);
  });
  on('pointerup',event=>{
    if(drag?.id!==event.pointerId)return;
    pan(event);const completed=drag;cancel();
    if(!completed.moved)onTap({building:completed.building,road:completed.road,point:localPoint(event)});
  });
  for(const name of ['pointercancel','lostpointercapture'])on(name,event=>{if(drag?.id===event.pointerId)cancel();});
  svg.ownerDocument.defaultView.addEventListener('blur',cancel,{signal});
  signal.addEventListener('abort',cancel,{once:true});
  on('wheel',event=>{
    if(!getView()||!event.deltaY)return;
    const anchor=localPoint(event);if(!anchor)return;
    event.preventDefault();cancel();
    const unit=event.deltaMode===1?16:event.deltaMode===2?svg.getBoundingClientRect().height:1;
    const pixels=Math.max(-240,Math.min(240,event.deltaY*unit));
    onZoom(Math.exp(pixels*.002),anchor);
  },{passive:false});
  return cancel;
}
