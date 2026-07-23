export function LoadingState() {
  return (
    <div className="loading-state" aria-live="polite" aria-label="Загружаю данные">
      <div className="empty-state-figure" aria-hidden="true">
        <img src="/catheadphones-large.png" alt="" />
      </div>
      <div className="loading-strip" aria-hidden="true">
        <span />
      </div>
    </div>
  );
}
