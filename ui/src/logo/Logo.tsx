type LogoSize = 'small' | 'medium' | 'large';
type LogoVariant = 'color' | 'light' | 'dark';

interface LogoProps {
  size?: LogoSize;
  variant?: LogoVariant;
}

function getWidth(size: LogoSize): number {
  switch (size) {
    case 'small':
      return 154;
    case 'medium':
      return 220;
    case 'large':
      return 320;
    default:
      return 220;
  }
}

export default function Logo({ size = 'medium', variant = 'color' }: LogoProps) {
  return (
    <img
      src="/golfone-logo.svg"
      alt="Golf One"
      className={`golfone-logo golfone-logo--${variant}`}
      width={getWidth(size)}
      draggable={false}
    />
  );
}
