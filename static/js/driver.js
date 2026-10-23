const driverSocket = ResQNow.socket();
let driverMap;
let driverMarker;
let watchId;

function initDriverMap() {
  driverMap = L.map('driver-map').setView([20, 0], 2);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
  }).addTo(driverMap);
}

function startGPS() {
  if (!navigator.geolocation) {
    document.querySelector('#driver-gps').textContent = 'GPS unavailable';
    return;
  }
  watchId = navigator.geolocation.watchPosition((position) => {
    const coordinates = position.coords;
    document.querySelector('#driver-gps').textContent = 'GPS live';
    if (driverMarker) {
      driverMarker.setLatLng([coordinates.latitude, coordinates.longitude]);
    } else {
      driverMarker = L.marker([coordinates.latitude, coordinates.longitude]).addTo(driverMap);
      driverMap.setView([coordinates.latitude, coordinates.longitude], 13);
    }
    Promise.resolve(driverSocket.emit('driver_location_update', {
      latitude: coordinates.latitude,
      longitude: coordinates.longitude,
      speed: coordinates.speed,
      heading: coordinates.heading,
      accuracy: coordinates.accuracy,
    })).catch((error) => {
      document.querySelector('#driver-gps').textContent = error.message;
    });
  }, () => {
    document.querySelector('#driver-gps').textContent = 'GPS permission needed';
  }, { enableHighAccuracy: true });
}

function loadRequests() {
  fetch('/api/bookings')
    .then((response) => response.json())
    .then((data) => {
      const list = document.querySelector('#request-list');
      const pending = data.bookings?.filter((booking) => booking.status === 'PENDING') || [];
      list.innerHTML = pending.length ? pending.map((booking) => `
        <article class="request-row">
          <div>
            <span class="badge ${booking.type === 'EMERGENCY' ? 'badge-red' : 'badge-blue'}">${booking.type.replace('_', ' ')}</span>
            <strong>Request #${booking.id}</strong>
            <small>Pickup coordinates ${booking.patient_latitude.toFixed(4)}, ${booking.patient_longitude.toFixed(4)}</small>
          </div>
          <div class="row-actions">
            <button class="button button-small button-ghost decision" data-id="${booking.id}" data-accept="false">Reject</button>
            <button class="button button-small button-green decision" data-id="${booking.id}" data-accept="true">Accept</button>
          </div>
        </article>`).join('') : '<div class="empty-state">No pending requests.</div>';
      document.querySelectorAll('.decision').forEach((button) => {
        button.onclick = () => decision(button.dataset.id, button.dataset.accept === 'true');
      });
    })
    .catch((error) => ResQNow.toast(error.message || 'Unable to load booking requests.', 'error'));
}

function decision(id, accept) {
  fetch(`/api/bookings/${id}/decision`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accept }),
  })
    .then((response) => response.json())
    .then((data) => {
      if (data.error) throw new Error(data.error);
      ResQNow.toast(`Booking #${id} ${accept ? 'accepted' : 'rejected'}.`);
      loadRequests();
    })
    .catch((error) => ResQNow.toast(error.message, 'error'));
}

function toggleOnline() {
  const button = document.querySelector('#online-toggle');
  const online = !button.classList.contains('on');
  button.disabled = true;
  Promise.resolve(driverSocket.emit(online ? 'driver_online' : 'driver_offline'))
    .then(() => {
      button.classList.toggle('on', online);
      document.querySelector('#driver-status').textContent = online ? 'ONLINE' : 'OFFLINE';
      if (online) {
        startGPS();
        loadRequests();
      } else if (watchId !== undefined) {
        navigator.geolocation.clearWatch(watchId);
        watchId = undefined;
      }
    })
    .catch((error) => ResQNow.toast(error.message, 'error'))
    .finally(() => { button.disabled = false; });
}

initDriverMap();
document.querySelector('#online-toggle').onclick = toggleOnline;
loadRequests();
driverSocket.on('emergency_request_received', loadRequests);
