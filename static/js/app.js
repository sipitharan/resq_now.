function postDriverAction(event, payload = {}) {
  let endpoint;
  let body;
  if (event === 'driver_online' || event === 'driver_offline') {
    endpoint = '/api/driver/status';
    body = { online: event === 'driver_online' };
  } else if (event === 'driver_location_update') {
    endpoint = '/api/driver/location';
    body = payload;
  } else {
    return null;
  }
  return fetch(endpoint, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(async (response) => {
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Realtime action failed.');
    return result;
  });
}

window.ResQNow = {
  toast(message, type = 'success') {
    const element = document.createElement('div');
    element.className = `flash ${type}`;
    element.textContent = message;
    const stack = document.querySelector('.flash-stack');
    if (stack) stack.append(element);
    else document.body.prepend(element);
    setTimeout(() => element.remove(), 4500);
  },

  socket() {
    const config = window.RESQNOW_REALTIME;
    if (config?.provider !== 'pusher') {
      const socket = io();
      socket.on('connect', () => {
        document.querySelectorAll('.connection').forEach((element) => {
          element.innerHTML = '<i></i> Secure connection';
        });
      });
      socket.on('notification', (event) => {
        if (event.message) this.toast(event.message);
      });
      return {
        on(event, callback) {
          socket.on(event, callback);
        },
        emit(event, payload) {
          const request = postDriverAction(event, payload);
          return request || socket.emit(event, payload);
        },
      };
    }

    if (!window.Pusher || !config.key || !config.cluster || !config.channel) {
      throw new Error('Realtime service is not configured for this account.');
    }

    const pusher = new Pusher(config.key, {
      cluster: config.cluster,
      channelAuthorization: {
        endpoint: config.authEndpoint,
        transport: 'ajax',
      },
    });
    const channel = pusher.subscribe(config.channel);
    channel.bind('pusher:subscription_succeeded', () => {
      document.querySelectorAll('.connection').forEach((element) => {
        element.innerHTML = '<i></i> Secure connection';
      });
      this.toast('Realtime connection established');
    });
    channel.bind('notification', (event) => {
      if (event.message) this.toast(event.message);
    });

    return {
      on(event, callback) {
        channel.bind(event, callback);
      },
      emit(event, payload = {}) {
        if (event === 'join_tracking') return Promise.resolve();
        return postDriverAction(event, payload)
          || Promise.reject(new Error(`Unsupported realtime action: ${event}`));
      },
    };
  },
};
