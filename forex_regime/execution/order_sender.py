"""MT5 market order send (semi-auto — validate risk before calling)."""

from __future__ import annotations

from typing import Any


def send_order(
    mt5_module: Any,
    signal: dict[str, Any],
    lot_size: float,
    *,
    comment: str = "QUANT_ENGINE",
) -> dict[str, Any]:
    send = getattr(mt5_module, "order_send", None)
    if send is None:
        return {"success": False, "ticket": None, "retcode": -1, "comment": "no order_send", "price_filled": None}

    sym = str(signal.get("symbol") or "")
    if not sym:
        return {"success": False, "ticket": None, "retcode": -1, "comment": "no symbol", "price_filled": None}

    direction = str(signal.get("direction") or "").upper()
    tick = mt5_module.symbol_info_tick(sym)
    if tick is None:
        return {"success": False, "ticket": None, "retcode": -1, "comment": "no tick", "price_filled": None}

    otype = (
        getattr(mt5_module, "ORDER_TYPE_BUY", 0)
        if direction == "BUY"
        else getattr(mt5_module, "ORDER_TYPE_SELL", 1)
    )
    price = float(tick.ask) if direction == "BUY" else float(tick.bid)

    req: dict[str, Any] = {
        "action": getattr(mt5_module, "TRADE_ACTION_DEAL", 1),
        "symbol": sym,
        "volume": float(lot_size),
        "type": int(otype),
        "price": price,
        "sl": float(signal.get("stop_loss") or 0),
        "tp": float(signal.get("take_profit") or 0),
        "deviation": 20,
        "magic": 20260001,
        "comment": str(comment)[:31],
        "type_time": getattr(mt5_module, "ORDER_TIME_GTC", 0),
        "type_filling": getattr(mt5_module, "ORDER_FILLING_IOC", 1),
    }

    try:
        result = send(req)
    except Exception as e:
        return {"success": False, "ticket": None, "retcode": -1, "comment": str(e), "price_filled": None}

    if result is None:
        return {"success": False, "ticket": None, "retcode": -1, "comment": "order_send returned None", "price_filled": None}

    done = getattr(mt5_module, "TRADE_RETCODE_DONE", 10009)
    rc = int(getattr(result, "retcode", -1))
    return {
        "success": rc == done,
        "ticket": getattr(result, "order", None),
        "retcode": rc,
        "comment": getattr(result, "comment", ""),
        "price_filled": getattr(result, "price", None),
    }
