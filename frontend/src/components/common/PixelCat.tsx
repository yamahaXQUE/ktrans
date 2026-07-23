type PixelBlock = {
  color: "outline" | "orange" | "cream" | "white" | "brown" | "tan" | "blush" | "shadow";
  x: number;
  y: number;
  w: number;
  h: number;
};

const pixel = 3;

const blocks: PixelBlock[] = [
  { color: "shadow", x: 8, y: 36, w: 46, h: 3 },

  { color: "outline", x: 7, y: 28, w: 4, h: 8 },
  { color: "outline", x: 9, y: 22, w: 5, h: 8 },
  { color: "outline", x: 12, y: 17, w: 5, h: 7 },
  { color: "outline", x: 16, y: 13, w: 7, h: 5 },
  { color: "outline", x: 22, y: 11, w: 10, h: 4 },
  { color: "outline", x: 31, y: 12, w: 5, h: 4 },
  { color: "outline", x: 34, y: 15, w: 4, h: 7 },
  { color: "outline", x: 33, y: 22, w: 4, h: 5 },
  { color: "outline", x: 29, y: 27, w: 8, h: 5 },
  { color: "outline", x: 19, y: 32, w: 14, h: 5 },
  { color: "outline", x: 11, y: 33, w: 10, h: 5 },
  { color: "outline", x: 8, y: 32, w: 4, h: 4 },

  { color: "orange", x: 10, y: 28, w: 5, h: 6 },
  { color: "orange", x: 12, y: 23, w: 6, h: 6 },
  { color: "orange", x: 15, y: 18, w: 8, h: 6 },
  { color: "orange", x: 19, y: 14, w: 9, h: 8 },
  { color: "cream", x: 23, y: 14, w: 10, h: 10 },
  { color: "white", x: 22, y: 22, w: 11, h: 8 },
  { color: "white", x: 18, y: 27, w: 14, h: 6 },
  { color: "tan", x: 13, y: 33, w: 8, h: 3 },
  { color: "brown", x: 11, y: 30, w: 4, h: 3 },
  { color: "brown", x: 12, y: 22, w: 4, h: 7 },
  { color: "brown", x: 16, y: 15, w: 4, h: 3 },
  { color: "tan", x: 21, y: 33, w: 7, h: 3 },

  { color: "outline", x: 25, y: 30, w: 8, h: 6 },
  { color: "brown", x: 27, y: 31, w: 5, h: 4 },
  { color: "tan", x: 25, y: 34, w: 4, h: 2 },

  { color: "outline", x: 32, y: 11, w: 4, h: 9 },
  { color: "outline", x: 35, y: 9, w: 5, h: 6 },
  { color: "outline", x: 39, y: 11, w: 6, h: 5 },
  { color: "outline", x: 45, y: 9, w: 5, h: 6 },
  { color: "outline", x: 49, y: 12, w: 5, h: 7 },
  { color: "outline", x: 53, y: 18, w: 4, h: 11 },
  { color: "outline", x: 50, y: 29, w: 4, h: 5 },
  { color: "outline", x: 45, y: 33, w: 6, h: 4 },
  { color: "outline", x: 36, y: 33, w: 9, h: 4 },
  { color: "outline", x: 31, y: 28, w: 7, h: 6 },
  { color: "outline", x: 29, y: 20, w: 7, h: 9 },

  { color: "orange", x: 35, y: 12, w: 5, h: 9 },
  { color: "orange", x: 40, y: 14, w: 10, h: 8 },
  { color: "cream", x: 46, y: 12, w: 4, h: 7 },
  { color: "white", x: 33, y: 20, w: 20, h: 13 },
  { color: "white", x: 38, y: 31, w: 10, h: 4 },
  { color: "brown", x: 32, y: 13, w: 5, h: 8 },
  { color: "brown", x: 35, y: 9, w: 5, h: 6 },
  { color: "tan", x: 42, y: 11, w: 3, h: 4 },
  { color: "blush", x: 37, y: 23, w: 4, h: 2 },
  { color: "outline", x: 41, y: 21, w: 4, h: 3 },
  { color: "outline", x: 49, y: 23, w: 5, h: 2 },

  { color: "outline", x: 28, y: 36, w: 24, h: 4 },
  { color: "white", x: 31, y: 34, w: 16, h: 4 },
  { color: "tan", x: 47, y: 34, w: 4, h: 3 },
  { color: "outline", x: 49, y: 34, w: 4, h: 4 },
];

const eyes = [
  { x: 42, y: 21 },
  { x: 50, y: 21 },
];

export function PixelCat() {
  return (
    <div className="pixel-cat-wrap" aria-hidden="true">
      <svg className="pixel-cat" viewBox="0 0 192 126" role="img">
        {blocks.map((block, index) => (
          <rect
            className={`cat-pixel cat-${block.color}`}
            height={block.h * pixel}
            key={`${block.color}-${block.x}-${block.y}-${index}`}
            width={block.w * pixel}
            x={block.x * pixel}
            y={block.y * pixel}
          />
        ))}

        {eyes.map((eye) => (
          <g key={`${eye.x}-${eye.y}`}>
            <rect
              className="cat-pixel cat-eye-open"
              height={3 * pixel}
              width={3 * pixel}
              x={eye.x * pixel}
              y={eye.y * pixel}
            />
            <rect
              className="cat-pixel cat-eye-closed"
              height={pixel}
              width={3 * pixel}
              x={eye.x * pixel}
              y={(eye.y + 1) * pixel}
            />
          </g>
        ))}
      </svg>
    </div>
  );
}
