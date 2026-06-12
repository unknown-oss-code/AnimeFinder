// بدل addFav بـ addFavorite
function addFavorite(id, btn){
    fetch('/add_favorite/' + id, { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        if (data.status === "ok") {
            showToast("✅ Added to Favorites!");
            btn.innerText = "✅ Added";
            btn.disabled = true;
            btn.style.background = "#555";
        } else if (data.status === "exists") {
            showToast("Already in Favorites ❤️");
        } else {
            showToast("Error ❌");
        }
    })
    .catch(()=> showToast("Error ❌"));
}

function removeFavorite(id) {
    fetch('/remove_favorite/' + id, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
        if (data.status === "ok") {
            showToast("🗑️ Removed!");
            setTimeout(() => location.reload(), 800);
        }
    })
    .catch(err => showToast("Error ❌"));
}