// Entry point: lazy page modules, the mode label, a subtle cell-track background, then the router.
import { $, app, isStatic, lazy, route, start } from './core.js';

const PAGES = {
  'home.js': ['home'], 'viewer.js': ['viewer'], 'cells.js': ['cells'], 'population.js': ['population'],
  'compare.js': ['compare'], 'data.js': ['data'], 'validate.js': ['validate'], 'about.js': ['about'],
};
lazy(Object.fromEntries(Object.entries(PAGES).flatMap(([file, names]) => names.map(n => [n, () => import('./' + file)]))));
route('notfound', () => { app().innerHTML = '<h1>Not found</h1><p><a href="#/">Back to the start</a></p>'; });

$('#mode').textContent = isStatic()
  ? 'static site: masks are read and analysed in your browser (JS ports of the Python analysis); the demo is synthetic'
  : 'local app: browser analysis plus the Python API on this computer';

// Background: a few soft "cells" drifting on persistent random walks. Off under prefers-reduced-motion.
function background(canvas) {
  if (!canvas || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  const g = canvas.getContext('2d');
  const fit = () => { canvas.width = innerWidth; canvas.height = innerHeight; };
  fit(); addEventListener('resize', fit);
  const cols = ['46,230,255', '255,79,216', '255,176,46'];
  const cs = Array.from({ length: 9 }, (_, i) => ({ x: Math.random() * innerWidth, y: Math.random() * innerHeight,
    a: Math.random() * 6.3, r: 18 + Math.random() * 22, c: cols[i % 3], trail: [] }));
  let last = 0;
  const tick = t => {
    requestAnimationFrame(tick);
    if (document.hidden || t - last < 50) return;
    last = t;
    g.clearRect(0, 0, canvas.width, canvas.height);
    for (const c of cs) {
      c.a += (Math.random() - 0.5) * 0.3; c.x += Math.cos(c.a) * 0.8; c.y += Math.sin(c.a) * 0.8;
      c.x = (c.x + canvas.width) % canvas.width; c.y = (c.y + canvas.height) % canvas.height;
      c.trail.push([c.x, c.y]); if (c.trail.length > 90) c.trail.shift();
      g.strokeStyle = `rgba(${c.c},.35)`; g.lineWidth = 1; g.beginPath();
      c.trail.forEach(([x, y], i) => { if (i && Math.abs(x - c.trail[i - 1][0]) < 50 && Math.abs(y - c.trail[i - 1][1]) < 50) g.lineTo(x, y); else g.moveTo(x, y); });
      g.stroke();
      g.fillStyle = `rgba(${c.c},.08)`; g.strokeStyle = `rgba(${c.c},.4)`;
      g.beginPath(); g.ellipse(c.x, c.y, c.r, c.r * 0.7, c.a, 0, 6.3); g.fill(); g.stroke();
    }
  };
  requestAnimationFrame(tick);
}
background($('#bg'));
start();
