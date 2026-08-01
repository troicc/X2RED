(() => {
  if (document.querySelector('script[data-x2red-light-lab="v12"]')) return;
  const script = document.createElement("script");
  script.src = "/static/light-content-lab-v12.js";
  script.dataset.x2redLightLab = "v12";
  document.head.appendChild(script);
})();
