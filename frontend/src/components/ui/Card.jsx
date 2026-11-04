export default function Card({ title, sub, right, className = '', children }) {
  return (
    <section className={'card ' + className}>
      <div className="ch">
        <div>
          <h3 className="ct">{title}</h3>
          {sub && <p className="cs">{sub}</p>}
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}
