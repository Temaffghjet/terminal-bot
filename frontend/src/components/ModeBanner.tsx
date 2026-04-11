/** Баннеры режима: testnet / dry_run / live (по спецификации). */
export default function ModeBanner({ testnet, dryRun }: { testnet: boolean; dryRun: boolean }) {
  if (!testnet && !dryRun) {
    return (
      <div className="bg-red-950/95 text-red-200 text-center py-2 text-sm font-semibold border-b border-red-700 tracking-wide">
        LIVE TRADING — реальные деньги
      </div>
    );
  }
  return (
    <div className="flex flex-col sm:flex-row border-b border-gray-800">
      {testnet ? (
        <div className="flex-1 bg-amber-950/85 text-amber-100 text-center py-1.5 text-xs font-medium">
          TESTNET MODE
        </div>
      ) : null}
      {dryRun ? (
        <div className="flex-1 bg-sky-950/85 text-sky-100 text-center py-1.5 text-xs font-medium">
          DRY RUN — ордера не отправляются
        </div>
      ) : null}
    </div>
  );
}
