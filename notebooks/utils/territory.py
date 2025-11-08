PAPER_SIZE = { #orientation: (width, height) in mm. Default is portrait
    "A4": (210, 297),  # mm
    "A3": (297, 420),  # mm
    "A2": (420, 594),  # mm 
    "A1": (594, 841),  # mm
    "A0": (841, 1189)  # mm
}

PORTRAIT = "portrait"
LANDSCAPE = "landscape"



class Territory(object):
    """
    Representa um território com geometria espacial e configurações de impressão.

    Esta classe calcula a extensão espacial da geometria, ajusta o tamanho do papel,
    define a orientação e determina o envelope de impressão com base na proporção e DPI.

    Atributos:
        id (str): Identificador único do território.
        geom (dict): Geometria no formato GeoJSON.
        offset (float): Margem relativa aplicada ao envelope de impressão.
        paper_size (tuple): Dimensões do papel em milímetros.
        dpi (int): Resolução em pontos por polegada.
        bbox (list): Bounding box no formato [minx, miny, maxx, maxy].
        orientation (str): 'portrait' ou 'landscape' conforme proporções.
    """
    def __init__(self, id, geom, offset=0.05, paper_size="A4", dpi=100):
        """
        Inicializa o objeto Territorio com geometria e parâmetros de impressão.

        Args:
            id (str): Identificador do território.
            geom (dict): Geometria GeoJSON.
            offset (float, opcional): Margem relativa para o envelope. Padrão: 0.05.
            paper_size (str or tuple, opcional): Nome do formato de papel (ex: 'A4') ou tupla (largura, altura) em mm.
            dpi (int, opcional): Resolução de saída em pontos por polegada. Padrão: 100.
        """        
        self.id = id
        self.geom = geom
        self.offset = offset
        self.dpi = dpi

        self.calculate_bbox()
        self.configure_paper_size(paper_size)
        self.calculate_printing_variables()


    def calculate_bbox(self):
        """
        Calcula a bounding box da geometria fornecida.

        Atribui atributos como `bbox`, `minx`, `miny`, `maxx`, `maxy`,
        além de `width` e `height` do território.
        """        
        def extrair_coords(coords):
            if isinstance(coords[0], (int, float)):
                return [coords]
            return [p for c in coords for p in extrair_coords(c)]

        pontos = extrair_coords(self.geom["coordinates"])
        xs, ys = zip(*pontos)

        self.bbox = [min(xs), min(ys), max(xs), max(ys)]
        self.minx, self.miny, self.maxx, self.maxy = self.bbox
        self.width = self.maxx - self.minx
        self.height = self.maxy - self.miny
            

    def configure_paper_size(self, paper_size):
        """
        Configura o tamanho do papel e define a orientação com base na geometria.

        Args:
            paper_size (str or tuple): Nome do formato ('A4', 'A3', etc.) ou tupla (largura, altura) em mm.

        Raises:
            ValueError: Se o nome do formato for inválido.
        """
        if isinstance(paper_size, tuple) and len(paper_size) == 2:
            self.paper_size = paper_size            
        elif isinstance(paper_size, str):
            paper_size = paper_size.upper()
            if paper_size in PAPER_SIZE:
                self.paper_size = PAPER_SIZE[paper_size]
            else:
                raise ValueError(f"Invalid paper size: {paper_size}. Available sizes: {list(PAPER_SIZE.keys())}")
        else:
            raise ValueError("paper_size must be a tuple (width, height) in mm or a valid paper size string (e.g., 'A4').")
        
        self.orientation = PORTRAIT
        if paper_size[0] > paper_size[1]:
            self.orientation = LANDSCAPE
            # self.paper_size = (self.paper_size[1], self.paper_size[0])  # Swap width and height for landscape


    def calculate_printing_variables(self):
        """
        Calcula o envelope de impressão e o tamanho do pixel em unidades de coordenada.

        Usa a proporção do papel e a margem definida para calcular uma nova bbox ajustada
        (`bbox_optimum`) e os tamanhos de pixel (`pixel_size_x`, `pixel_size_y`).
        """
        paper_width_mm, paper_height_mm = self.paper_size
        self.paper_width_px = self.mm_to_px(paper_width_mm)
        self.paper_height_px = self.mm_to_px(paper_height_mm)

        aspect = paper_width_mm / paper_height_mm

        # Adicionar margem e ajustar proporção
        if self.orientation == PORTRAIT:
            new_width = self.width * (1 + 2 * self.offset)
            new_height = new_width / aspect
        else:
            new_height = self.height * (1 + 2 * self.offset)
            new_width = new_height * aspect

        # Calcular bbox centrado
        cx = (self.minx + self.maxx) / 2
        cy = (self.miny + self.maxy) / 2
        self.minx_optimum = cx - new_width / 2
        self.maxx_optimum = cx + new_width / 2
        self.miny_optimum = cy - new_height / 2
        self.maxy_optimum = cy + new_height / 2
        self.bbox_optimum = {
            "type": "Polygon",
            "coordinates": [[
                [self.minx_optimum, self.miny_optimum],
                [self.minx_optimum, self.maxy_optimum],
                [self.maxx_optimum, self.maxy_optimum],
                [self.maxx_optimum, self.miny_optimum],
                [self.minx_optimum, self.miny_optimum]  # fechar o polígono
            ]]
        }

        # Calcular pixel size
        self.pixel_size_x = (self.maxx_optimum - self.minx_optimum) / self.paper_width_px
        self.pixel_size_y = (self.maxy_optimum - self.miny_optimum) / self.paper_height_px


    def mm_to_px(self, mm):
        """
        Converte um valor de milímetros para pixels com base no DPI.

        Args:
            mm (float): Valor em milímetros.

        Returns:
            int: Valor correspondente em pixels.
        """
        return round(mm / 25.4 * self.dpi)

    def __str__(self):
        return (
            f"Território '{self.id}':\n"
            f"  - Tamanho geométrico: {self.width:.2f} x {self.height:.2f} unidades\n"
            f"  - BBox: [{self.minx:.4f}, {self.miny:.4f}, {self.maxx:.4f}, {self.maxy:.4f}]\n"
            f"  - Papel: {self.paper_size[0]} x {self.paper_size[1]} mm ({self.orientation})\n"
            f"  - DPI: {self.dpi}\n"
            f"  - Resolução: {self.paper_width_px} x {self.paper_height_px} px\n"
            f"  - Tamanho do pixel: {self.pixel_size_x:.6f} x {self.pixel_size_y:.6f} unidades/px\n"
            f"  - BBox otimizada: [{self.minx_optimum:.4f}, {self.miny_optimum:.4f}, {self.maxx_optimum:.4f}, {self.maxy_optimum:.4f}]"
        )