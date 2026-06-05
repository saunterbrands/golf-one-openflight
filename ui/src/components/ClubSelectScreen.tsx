import { ALL_CLUBS, CLUBS_BY_TYPE } from '../data/clubs';
import './ClubSelectScreen.css';

interface ClubSelectScreenProps {
  /** Currently selected club id; pre-highlighted on the grid. */
  selectedClub: string;
  /** Called with the chosen club id when the user picks a club. */
  onSelect: (club: string) => void;
  /** Called when the user starts without changing the current club. */
  onSkip: () => void;
}

/**
 * Full-screen interstitial shown on app load so the user confirms which club
 * they're hitting before the first shot. Dismissible via Skip, which keeps the
 * current (default) club.
 */
export function ClubSelectScreen({ selectedClub, onSelect, onSkip }: ClubSelectScreenProps) {
  const selectedLabel = ALL_CLUBS.find((c) => c.id === selectedClub)?.label ?? 'DR';

  return (
    <div className="club-select" role="dialog" aria-modal="true" aria-label="Select your club">
      <div className="club-select__panel">
        <h1 className="club-select__title">Select your club</h1>
        <p className="club-select__subtitle">Choose the club you're hitting to start your session.</p>

        {Object.entries(CLUBS_BY_TYPE).map(([type, clubs]) => (
          <div className="club-select__section" key={type}>
            <span className="club-select__section-title">{type}</span>
            <div className="club-select__grid">
              {clubs.map((club) => (
                <button
                  key={club.id}
                  className={`club-select__option ${selectedClub === club.id ? 'club-select__option--selected' : ''}`}
                  onClick={() => onSelect(club.id)}
                >
                  {club.label}
                </button>
              ))}
            </div>
          </div>
        ))}

        <button className="club-select__skip" onClick={onSkip}>
          Skip — keep {selectedLabel}
        </button>
      </div>
    </div>
  );
}
