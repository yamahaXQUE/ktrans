type EmptyStateProps = {
  message?: string;
};

export function EmptyState({ message = "тут пока ничего нет" }: EmptyStateProps) {
  return (
    <div className="empty-state">
      <div className="empty-state-figure" aria-hidden="true">
        <img src="/catheadphones-large.png" alt="" />
      </div>
      <p>{message}</p>
    </div>
  );
}
