(() => {
  const menu=document.getElementById('menu'),sidebar=document.getElementById('sidebar');
  const close=document.getElementById('sidebar-close'),backdrop=document.getElementById('sidebar-backdrop');
  if(!menu||!sidebar)return;
  const closeSidebar=()=>{sidebar.classList.remove('open');backdrop?.classList.remove('visible');document.body.classList.remove('navigation-open');menu.setAttribute('aria-expanded','false')};
  const openSidebar=()=>{sidebar.classList.add('open');backdrop?.classList.add('visible');document.body.classList.add('navigation-open');menu.setAttribute('aria-expanded','true')};
  menu.addEventListener('click',()=>sidebar.classList.contains('open')?closeSidebar():openSidebar());
  close?.addEventListener('click',closeSidebar);
  backdrop?.addEventListener('click',closeSidebar);
  sidebar.querySelectorAll('.nav a').forEach(link=>link.addEventListener('click',closeSidebar));
  document.addEventListener('keydown',event=>{if(event.key==='Escape')closeSidebar()});
})();
