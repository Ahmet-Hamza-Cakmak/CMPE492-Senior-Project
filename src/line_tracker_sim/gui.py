"""Desktop scenario form using Python's standard Tk toolkit."""

from pathlib import Path

from .scenario import Corridor, Scenario
from .simulation import build_model, example_robot, run


def main():
    try:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk
    except ImportError:
        raise SystemExit("Tkinter is required. On Ubuntu/Debian install python3-tk.")

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(f"A desktop display is required to open the scenario GUI: {exc}")
    root.title("Line tracker scenario")
    root.geometry("700x650")
    frame = ttk.Frame(root, padding=16)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    robot = tk.StringVar(value=str(example_robot()))
    count = tk.StringVar(value="3")
    width = tk.StringVar(value="0.8")
    line_width = tk.StringVar(value="0.025")
    auto_follow = tk.BooleanVar(value=True)
    ttk.Label(frame, text="Robot MJCF XML").grid(row=0, column=0, sticky="w")
    ttk.Entry(frame, textvariable=robot).grid(row=0, column=1, sticky="ew")

    def browse():
        path = filedialog.askopenfilename(title="Select robot model", filetypes=[("MuJoCo XML", "*.xml")])
        if path:
            robot.set(path)

    ttk.Button(frame, text="Browse…", command=browse).grid(row=0, column=2)
    ttk.Label(frame, text="Keep included XML, meshes and textures beside the model in their original folders.",
              wraplength=620).grid(row=1, column=0, columnspan=3, sticky="w", pady=8)
    ttk.Label(frame, text="Number of corridors").grid(row=2, column=0, sticky="w")
    ttk.Spinbox(frame, from_=1, to=100, textvariable=count, width=8).grid(row=2, column=1, sticky="w")
    for row, label, variable in ((3, "Corridor width (m)", width), (4, "Line width (m)", line_width)):
        ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w")
        ttk.Entry(frame, textvariable=variable, width=10).grid(row=row, column=1, sticky="w")
    ttk.Label(frame, text="Angles are relative turns: 0° straight, + left, − right. First section faces +X.",
              wraplength=620).grid(row=5, column=0, columnspan=3, sticky="w", pady=10)
    container = ttk.Frame(frame)
    container.grid(row=6, column=0, columnspan=3, sticky="nsew")
    frame.rowconfigure(6, weight=1)
    canvas = tk.Canvas(container, highlightthickness=0)
    scroll = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
    canvas.configure(yscrollcommand=scroll.set)
    canvas.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    rows = ttk.Frame(canvas)
    canvas.create_window((0, 0), window=rows, anchor="nw")
    rows.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
    values = []

    def update_rows():
        try:
            number = int(count.get())
            if not 1 <= number <= 100:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid count", "Enter a whole number between 1 and 100.")
            return False
        old = [(length.get(), turn.get()) for length, turn in values]
        for widget in rows.winfo_children():
            widget.destroy()
        values.clear()
        for col, title in enumerate(("Corridor", "Length (m)", "Turn (degrees)")):
            ttk.Label(rows, text=title).grid(row=0, column=col, padx=10)
        for index in range(number):
            length, turn = old[index] if index < len(old) else ("2.0", "0")
            lv, tv = tk.StringVar(value=length), tk.StringVar(value=turn if index else "0")
            values.append((lv, tv))
            ttk.Label(rows, text=str(index + 1)).grid(row=index + 1, column=0)
            ttk.Entry(rows, textvariable=lv, width=16).grid(row=index + 1, column=1, padx=10, pady=3)
            ttk.Entry(rows, textvariable=tv, width=16, state="normal" if index else "disabled").grid(
                row=index + 1, column=2, padx=10, pady=3)
        return True

    ttk.Button(frame, text="Apply count", command=update_rows).grid(row=2, column=2)
    ttk.Label(frame, text="Place your robot at the origin, facing +X, with its wheels on z=0.\n"
              "Automatic driving uses ideal track sensing and supports the bundled robot only.",
              wraplength=620).grid(row=7, column=0, columnspan=3, pady=10, sticky="w")
    follow_box = ttk.Checkbutton(frame, text="Sample robot: automatically follow the line", variable=auto_follow)
    follow_box.grid(row=8, column=0, columnspan=3, sticky="w")

    def robot_changed(*_):
        bundled = Path(robot.get()).expanduser().resolve() == example_robot().resolve()
        auto_follow.set(bundled)
        follow_box.configure(state="normal" if bundled else "disabled")

    robot.trace_add("write", robot_changed)

    def launch():
        if not update_rows():
            return
        try:
            scenario = Scenario(tuple(Corridor(float(l.get()), float(t.get())) for l, t in values),
                                float(width.get()), float(line_width.get()))
            model = build_model(robot.get(), scenario)
        except Exception as exc:
            messagebox.showerror("Cannot build scenario", str(exc))
            return
        root.withdraw()
        try:
            run(model, scenario, auto_follow=auto_follow.get())
        except Exception as exc:
            messagebox.showerror("Simulation error", str(exc), parent=root)
        finally:
            root.deiconify()

    ttk.Button(frame, text="Open MuJoCo simulation", command=launch).grid(row=9, column=0, columnspan=3, pady=5)
    update_rows()
    root.mainloop()
