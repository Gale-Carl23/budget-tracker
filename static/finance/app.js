(() => {
  const menu=document.getElementById('menu'),sidebar=document.getElementById('sidebar');
  if(menu&&sidebar) menu.addEventListener('click',()=>sidebar.classList.toggle('open'));
})();
