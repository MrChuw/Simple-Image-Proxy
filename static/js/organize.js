async function organizeImages() {
    var grid = document.querySelector('.grid');
    var iso;

    // Inicializar o Isotope
    iso = new Isotope(grid, {
        itemSelector: '.grid-item',
        percentPosition: true,
        masonry: {
            layoutMode: 'packery',
            columnWidth: '.grid-sizer'
        }
    });

    // Certifique-se de que as imagens estejam carregadas antes de ajustar o layout
    imagesLoaded(grid).on('progress', function() {
        // Ajusta o layout do Isotope após o carregamento de cada imagem
        iso.layout();
    });
}