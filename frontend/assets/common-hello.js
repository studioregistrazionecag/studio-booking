const API = location.origin;
const auth = {
  Authorization: `Bearer ${localStorage.getItem('token')}`,
  'Content-Type': 'application/json'
};

if (!localStorage.getItem('token')) {
  location.href = '/frontend/auth/login.html';
}

function logout() {
  localStorage.removeItem('token');
  location.href = '/frontend/auth/login.html';
}

(async function hello() {
  try {
    const r = await fetch(`${API}/auth/me`, { headers: auth });
    const u = r.ok ? await r.json() : null;
    if (u?.display_name) {
      document.getElementById('hello').textContent = `Ciao, ${u.display_name}`;
    }
  } catch (err) {
    console.error('Errore nel recupero del nome utente', err);
  }
})();