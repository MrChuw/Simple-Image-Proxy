async function fetchLinks() {
    const folder = window.location.pathname.split('/').pop(); // Assumindo que a pasta está na URL
    const wsUrl = `ws://${window.location.host}/ws/${folder}`;
    let ws = new WebSocket(wsUrl);

    ws.onopen = function() {
        console.log('WebSocket connection opened');
    };

    ws.onmessage = function(event) {
        const lines = event.data.split("\n");

        for (let line of lines) {
            if (line) {
                const [link, fileType] = line.split("\t");
                if (link && fileType) {
                    const grid_item = document.createElement("div");
                    grid_item.classList.add("grid-item");

                    let mediaElement;

                    if (fileType.startsWith("image/")) {
                        mediaElement = document.createElement("img");
                        mediaElement.src = link;
                        mediaElement.classList.add("gallery-item");
                    } else if (fileType.startsWith("video/")) {
                        mediaElement = document.createElement("video");
                        mediaElement.src = link;
                        mediaElement.width = "320";
                        mediaElement.controls = true;
                        mediaElement.classList.add("gallery-item");
                        mediaElement.classList.add("gallery-video");
                    } else if (fileType.startsWith("audio/")) {
                        mediaElement = document.createElement("audio");
                        mediaElement.src = link;
                        mediaElement.width = "320";
                        mediaElement.controls = true;
                        mediaElement.classList.add("gallery-item");
                    }

                    if (mediaElement) {
                        const linkElement = document.createElement("a");
                        linkElement.href = link;
                        linkElement.target = "_blank";
                        linkElement.appendChild(mediaElement);
                        grid_item.appendChild(linkElement);

                        // Adicionar link (e mídia) à galeria
                        const gallery = document.getElementById("gallery");
                        gallery.appendChild(grid_item);
                    }
                }
            }
        }
    };

    ws.onerror = function(error) {
        console.error('WebSocket error:', error);
    };

    ws.onclose = function(event) {
        console.log('WebSocket connection closed:', event.reason);
        // Tentar reconectar após um breve intervalo
        setTimeout(() => {
            console.log('Attempting to reconnect...');
            fetchLinks();
        }, 5000); // 5 segundos de intervalo para reconectar
    };
}
