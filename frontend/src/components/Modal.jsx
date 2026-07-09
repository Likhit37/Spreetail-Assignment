export default function Modal({ title, onClose, children }) {
  return (
    <div className="modal" onClick={onClose}>
      <div className="card modal-body" onClick={(e) => e.stopPropagation()}>
        <div className="row between" style={{ marginTop: 0 }}>
          <h3 style={{ margin: 0 }}>{title}</h3>
          <button className="link" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
