async function fetchSongs() {
  const res = await fetch('/api/songs');
  const songs = await res.json();
  const container = document.getElementById('songs');
  if (!container) return;
  container.innerHTML = "";

  songs.forEach(s => {
    const card = document.createElement('div');
    card.className = "song-card fade-in";
    card.innerHTML = `
      <h3>${s.title}</h3>
      <small>${s.comments.length} نظر</small>
      <div class="comments">
        ${s.comments.map(c => `<p><strong>${c.user}</strong>: ${c.comment}</p>`).join('')}
      </div>
    `;
    container.appendChild(card);
  });
}

setInterval(fetchSongs, 5000);

 