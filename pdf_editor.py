import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import fitz  # PyMuPDF
import os
from PIL import Image, ImageTk
import io
from functools import partial
import datetime
import requests
import getpass
import socket
import threading
import time
import queue
#from pylovepdf.ilovepdf import ILovePdf

# Try to import tkinterdnd2 for drag and drop functionality
try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
    DRAG_DROP_AVAILABLE = True
except ImportError:
    DRAG_DROP_AVAILABLE = False
    print("tkinterdnd2 not available. Install with: pip install tkinterdnd2")

class PDFEditorApp(ctk.CTk if not DRAG_DROP_AVAILABLE else TkinterDnD.Tk):
    def __init__(self):
        # Expiry check
        expiry_date = datetime.date(2026, 12, 31)
        if datetime.date.today() > expiry_date:
            tk.messagebox.showerror("App Expired", "This version of the PDF Editor has expired. Please contact Midhun Das A R for an updated version.")
            self.destroy()
            return
        super().__init__()
        self.title("PDFY")
        self.geometry("1200x800")
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        self.pdf_path = None
        self.pdf_temp_path = None  # Track the temp file path
        self.pdf_doc = None
        self.selected_page = None
        self.thumbnail_images = []  # Keep references to avoid garbage collection
        self.thumbnail_buttons = []  # Store references to thumbnail buttons
        self.thumbnail_labels = []   # Store references to page number labels
        self.current_pil_image = None  # Store the current PIL image for resizing
        self.drag_data = {'from_idx': None, 'start_y': None, 'press_y': None, 'click_timer': None, 'moved': False, 'highlight_line': None, 'target_idx': None}
        self.undo_stack = []  # Store previous PDF states as bytes
        self.redo_stack = []  # Store redo PDF states as bytes
        self.is_merged_pdf = False  # Track if current PDF is a merged temp
        # self.notification_label = None  # Remove label, use floating notification
        self.protocol("WM_DELETE_WINDOW", self.on_close)  # Ensure temp file is deleted on close
        
        self.thumb_queue = queue.Queue()
        self._check_thumbnail_queue()  # Start polling loop
        
        self.init_ui()
        # Fix full screen reliably
        self.after(100, lambda: self.state('zoomed'))
        # Bind arrow keys for page navigation
        self.bind('<Left>', self._on_arrow_key)
        self.bind('<Right>', self._on_arrow_key)
        self.bind('<Up>', self._on_arrow_key)
        self.bind('<Down>', self._on_arrow_key)
        # Bind undo/redo shortcuts
        self.bind_all('<Control-z>', self._on_undo)
        self.bind_all('<Control-y>', self._on_redo)

    def init_ui(self):
        # Sidebar for file actions
        sidebar = ctk.CTkFrame(self, width=200, fg_color="#222831")
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=0, pady=0)
        open_btn = ctk.CTkButton(sidebar, text="Open PDF", command=self.open_pdf)
        open_btn.pack(pady=20, padx=20, fill=tk.X)
        self.save_over_btn = ctk.CTkButton(sidebar, text="Save", command=self.save_overwrite)
        self.save_over_btn.pack(pady=10, padx=20, fill=tk.X)
        save_btn = ctk.CTkButton(sidebar, text="Save As", command=self.save_pdf)
        save_btn.pack(pady=10, padx=20, fill=tk.X)
        insert_btn = ctk.CTkButton(sidebar, text="Insert", command=self.insert_page)
        insert_btn.pack(pady=10, padx=20, fill=tk.X)
        self.delete_btn = ctk.CTkButton(sidebar, text="Delete", command=self.delete_page)
        self.delete_btn.pack(pady=10, padx=20, fill=tk.X)
        multi_delete_btn = ctk.CTkButton(sidebar, text="Delete Multiple", command=self.delete_multiple_pages)
        multi_delete_btn.pack(pady=10, padx=20, fill=tk.X)
        reorder_btn = ctk.CTkButton(sidebar, text="Reorder", command=self.reorder_pages)
        reorder_btn.pack(pady=10, padx=20, fill=tk.X)
        rotate_btn = ctk.CTkButton(sidebar, text="Rotate", command=self.rotate_page)
        rotate_btn.pack(pady=10, padx=20, fill=tk.X)
        merge_btn = ctk.CTkButton(sidebar, text="Merge", command=self.merge_pdfs)
        merge_btn.pack(pady=10, padx=20, fill=tk.X)
        compress_btn = ctk.CTkButton(sidebar, text="Compress", command=self.compress_pdf)
        compress_btn.pack(pady=10, padx=20, fill=tk.X)
        # Add Convert button
        convert_btn = ctk.CTkButton(sidebar, text="Convert", command=self.convert_page)
        convert_btn.pack(pady=10, padx=20, fill=tk.X)
        # Removed Text Edit button and features
        about_btn = ctk.CTkButton(sidebar, text="About", command=self.show_about)
        about_btn.pack(pady=10, padx=20, fill=tk.X)
        # Notification label removed

        # Main area for page thumbnails and preview
        main_frame = ctk.CTkFrame(self, fg_color="#222831")
        main_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Add path display at the top
        path_frame = ctk.CTkFrame(main_frame, fg_color="#393e46", height=40)
        path_frame.pack(side=tk.TOP, fill=tk.X, pady=(0, 10))
        path_frame.pack_propagate(False)
        
        self.path_label = ctk.CTkLabel(path_frame, text="No PDF opened", 
                                      font=("Arial", 11), text_color="#cccccc",
                                      anchor="w", cursor="hand2")
        self.path_label.pack(side=tk.LEFT, padx=15, pady=10, fill=tk.X, expand=True)
        self.path_label.bind('<Button-1>', self._open_pdf_folder)
        
        # Add a small folder icon
        folder_label = ctk.CTkLabel(path_frame, text="📁", font=("Arial", 14), 
                                   text_color="#1976D2", cursor="hand2")
        folder_label.pack(side=tk.RIGHT, padx=(0, 15), pady=10)
        folder_label.bind('<Button-1>', self._open_pdf_folder)

        # Thumbnails scrollable frame
        thumb_frame = ctk.CTkFrame(main_frame, width=240, fg_color="#222831")
        thumb_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0,10), pady=0)
        self.thumb_canvas = tk.Canvas(thumb_frame, width=220, bg="#393e46", highlightthickness=0, bd=0, relief=tk.FLAT)
        self.thumb_scrollbar = ctk.CTkScrollbar(thumb_frame, orientation=tk.VERTICAL, command=self.thumb_canvas.yview)
        self.thumb_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.thumb_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.thumb_canvas.configure(yscrollcommand=self.thumb_scrollbar.set)
        self.thumbs_inner = tk.Frame(self.thumb_canvas, bg="#393e46")
        self.thumb_canvas.create_window((0,0), window=self.thumbs_inner, anchor="nw")
        self.thumbs_inner.bind("<Configure>", lambda e: self.thumb_canvas.configure(scrollregion=self.thumb_canvas.bbox("all")))
        self.thumb_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # PDF page preview (no scrollbars)
        preview_frame = ctk.CTkFrame(main_frame, fg_color="#222831")
        preview_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.preview_canvas = tk.Canvas(preview_frame, bg="#23272e", width=800, height=1000, highlightthickness=0, bd=0, relief=tk.FLAT)
        self.preview_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.preview_canvas.bind("<MouseWheel>", self._on_preview_page_scroll)
        self.preview_canvas.bind("<Configure>", self._on_preview_canvas_resize)
        # Enable native drag and drop for PDF files
        self._setup_drag_drop()
        # Page number display and Go to Page
        nav_frame = ctk.CTkFrame(preview_frame, fg_color="#23272e")
        nav_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=8)
        self.page_label = ctk.CTkLabel(nav_frame, text="Page 0 / 0", font=("Arial", 12), text_color="#eeeeee")
        self.page_label.pack(side=tk.LEFT, padx=10)
        ctk.CTkLabel(nav_frame, text="Go to:", font=("Arial", 12), text_color="#eeeeee").pack(side=tk.LEFT, padx=(20,2))
        self.goto_entry = ctk.CTkEntry(nav_frame, width=50, font=("Arial", 12))
        self.goto_entry.pack(side=tk.LEFT)
        self.goto_entry.bind('<Return>', lambda event: self._goto_page())
        goto_btn = ctk.CTkButton(nav_frame, text="Go", width=40, command=self._goto_page)
        goto_btn.pack(side=tk.LEFT, padx=5)

    def _on_mousewheel(self, event):
        self.thumb_canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _on_preview_page_scroll(self, event):
        if not self.pdf_doc:
            return
        if event.delta > 0:
            # Scroll up: previous page
            if self.selected_page is not None and self.selected_page > 0:
                self.show_page(self.selected_page - 1)
        elif event.delta < 0:
            # Scroll down: next page
            if self.selected_page is not None and self.selected_page < len(self.pdf_doc) - 1:
                self.show_page(self.selected_page + 1)

    def _on_preview_canvas_resize(self, event):
        # Re-render the current page to fit the new canvas size
        if self.current_pil_image is not None:
            self._display_pil_image_on_canvas(self.current_pil_image)

    def open_pdf(self, path=None, is_merged=False):
        import shutil, tempfile, uuid
        if path is None:
            path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
            if not path:
                return
        # Clean up previous temp file if any
        if self.pdf_doc:
            try:
                self.pdf_doc.close()
            except Exception:
                pass
        if self.pdf_temp_path and os.path.exists(self.pdf_temp_path):
            try:
                os.remove(self.pdf_temp_path)
            except Exception:
                pass
        try:
            # Always create temp file in system temp dir
            base, ext = os.path.splitext(os.path.basename(path))
            temp_dir = tempfile.gettempdir()
            temp_path = os.path.join(temp_dir, f"pdfeditor_{uuid.uuid4().hex}{ext}")
            shutil.copy2(path, temp_path)
            self.pdf_temp_path = temp_path
            self.pdf_doc = fitz.open(self.pdf_temp_path)
            self.pdf_path = path
            self.is_merged_pdf = is_merged
            self.refresh_thumbnails()
            self.show_page(0)
            self.undo_stack.clear()
            self.redo_stack.clear()
            self._update_undo_redo_btn_state()
            self._update_save_btn_state()
            self._update_path_display()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to open PDF: {e}")
            self._update_path_display()

    def save_pdf(self):
        if not self.pdf_doc:
            messagebox.showwarning("No PDF", "Open a PDF first.")
            return
        # Prompt for page selection
        input_dialog = tk.Toplevel(self)
        input_dialog.title("Save As - Page Selection")
        input_dialog.geometry("350x150")
        input_dialog.grab_set()
        label = tk.Label(input_dialog, text="Enter pages to save (e.g. 1,3,5-7). Leave blank for all:", font=("Arial", 11))
        label.pack(pady=10, padx=10)
        entry = tk.Entry(input_dialog, font=("Arial", 12))
        entry.pack(pady=5, padx=10, fill=tk.X)
        entry.focus_set()
        result = {'pages': None}
        def on_ok():
            raw = entry.get().replace(' ', '')
            if not raw:
                result['pages'] = None  # All pages
            else:
                try:
                    pages = set()
                    for part in raw.split(','):
                        if '-' in part:
                            start, end = part.split('-')
                            start, end = int(start), int(end)
                            if start > end:
                                raise ValueError
                            pages.update(range(start, end+1))
                        else:
                            pages.add(int(part))
                    # Convert to zero-based and sort
                    pages = [p-1 for p in sorted(pages) if 1 <= p <= len(self.pdf_doc)]
                    if not pages:
                        raise ValueError
                    result['pages'] = pages
                except Exception:
                    messagebox.showerror("Error", "Invalid input. Use e.g. 1,7,8 or 5-9.", parent=input_dialog)
                    return
            input_dialog.destroy()
        ok_btn = tk.Button(input_dialog, text="OK", command=on_ok, width=10)
        ok_btn.pack(pady=10)
        input_dialog.transient(self)
        input_dialog.wait_window()
        # After dialog
        pages = result['pages']
        path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
        if not path:
            return
        try:
            if pages is None:
                self.pdf_doc.save(path)
            else:
                # Save only selected pages
                new_pdf = fitz.open()
                for p in pages:
                    new_pdf.insert_pdf(self.pdf_doc, from_page=p, to_page=p)
                new_pdf.save(path)
                new_pdf.close()
            messagebox.showinfo("Saved", f"PDF saved to {path}")
            # If in merge mode, load the saved PDF as a regular PDF
            if self.is_merged_pdf:
                self.open_pdf(path, is_merged=False)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF: {e}")

    def save_overwrite(self):
        if not self.pdf_doc or not self.pdf_path:
            messagebox.showwarning("No PDF", "No PDF file is currently open.")
            return
        import os, tempfile
        confirm = messagebox.askyesno("Overwrite PDF", f"Are you sure you want to overwrite the current PDF?\n{self.pdf_path}")
        if not confirm:
            return
        try:
            # Save directly to the original path
            self.pdf_doc.save(self.pdf_path)
            messagebox.showinfo("Saved", f"PDF overwritten: {self.pdf_path}")
        except (PermissionError, OSError) as e:
            # Offer Save As fallback
            messagebox.showwarning("Access Denied", f"Could not overwrite the original PDF.\nReason: {e}\n\nYou can save to a different location.")
            path = filedialog.asksaveasfilename(defaultextension=".pdf", filetypes=[("PDF Files", "*.pdf")])
            if not path:
                return
            try:
                self.pdf_doc.save(path)
                messagebox.showinfo("Saved", f"PDF saved to {path}")
            except Exception as e2:
                messagebox.showerror("Error", f"Failed to save PDF: {e2}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save PDF: {e}")

    def refresh_thumbnails(self):
        # Clear previous thumbnails
        for widget in self.thumbs_inner.winfo_children():
            widget.destroy()
        self.thumbnail_images.clear()
        self.thumbnail_buttons = []
        self.thumbnail_labels = []
        
        # Cancel running thread
        if hasattr(self, '_thumb_thread_stop_event'):
            self._thumb_thread_stop_event.set()
        
        if not self.pdf_doc or not self.pdf_path:
            return
        
        # Track loaded thumbnails
        self._loaded_thumbnails = set()
        
        thumb_width = 180
        # Create placeholder frames for ALL pages
        for i in range(len(self.pdf_doc)):
            self.thumbnail_buttons.append(None)
            self.thumbnail_labels.append(None)
            self.thumbnail_images.append(None)
            
            # Placeholder frame
            frame = tk.Frame(self.thumbs_inner, bg="#d0d0d0")
            frame.grid(row=i, column=0, pady=2, padx=2, sticky="n")
            
            # Gray placeholder box
            placeholder = tk.Label(frame, text="", bg="#e0e0e0", width=int(thumb_width/7), height=10, relief=tk.FLAT)
            placeholder.pack(side=tk.TOP)
            
            # Page number
            label = tk.Label(frame, text=f"{i+1}", font=("Arial", 10, "bold"), bg="#d0d0d0", fg="#666")
            label.pack(side=tk.TOP, pady=(1,0))
            
            frame._page_index = i
            frame._placeholder = placeholder
        
        # Load initial window
        self._update_thumbnail_window(0)

    def _update_thumbnail_window(self, center_page, window_size=8):
        """Load thumbnails for pages near center_page."""
        if not self.pdf_doc:
            return
            
        total_pages = len(self.pdf_doc)
        start = max(0, center_page - window_size)
        end = min(total_pages, center_page + window_size + 1)
        
        # Pages to load
        pages_to_load = []
        for i in range(start, end):
            if i not in self._loaded_thumbnails:
                pages_to_load.append(i)
        
        if not pages_to_load:
            return
        
        # Cancel previous thread
        if hasattr(self, '_thumb_thread_stop_event'):
            self._thumb_thread_stop_event.set()
        
        self._thumb_thread_stop_event = threading.Event()
        threading.Thread(target=self._generate_thumbnails_background, 
                         args=(self.pdf_path, pages_to_load, self._thumb_thread_stop_event), 
                         daemon=True).start()

    def _generate_thumbnails_background(self, path, page_indices, stop_event):
        try:
            doc = fitz.open(path)
            thumb_width = 180
            
            for i in page_indices:
                if stop_event.is_set():
                    break
                
                if i >= len(doc):
                    continue
                    
                page = doc[i]
                pix = page.get_pixmap(matrix=fitz.Matrix(0.25, 0.25))
                img_data = pix.tobytes("png")
                
                img = Image.open(io.BytesIO(img_data))
                aspect = img.height / img.width
                thumb_height = int(thumb_width * aspect)
                img_resized = img.resize((thumb_width, thumb_height), Image.LANCZOS)
                
                # Push to queue instead of direct update
                self.thumb_queue.put((i, img_resized, thumb_width, thumb_height))
                
                # Mark as loaded in background thread to avoid re-queueing
                self._loaded_thumbnails.add(i)
                    
            doc.close()
            # Restore highlight after loading
            self.after(0, self._highlight_selected_thumbnail)
            
        except Exception as e:
            print(f"Thumbnail thread error: {e}")

    def _check_thumbnail_queue(self):
        """Poll the thumbnail queue and update UI safely."""
        try:
            # Process up to 5 thumbnails per tick to stay smooth
            for _ in range(5):
                try:
                    # Get item without blocking
                    item = self.thumb_queue.get_nowait()
                    index, pil_img, w, h = item
                    self._add_single_thumbnail(index, pil_img, w, h)
                except queue.Empty:
                    break
        except Exception:
            pass
        finally:
            # Re-schedule check in 50ms
            self.after(50, self._check_thumbnail_queue)

    def _add_single_thumbnail(self, index, pil_img, width, height):
        if index >= len(self.thumbnail_buttons):
            return
            
        tk_img = ImageTk.PhotoImage(pil_img)
        self.thumbnail_images[index] = tk_img 
        
        frame = tk.Frame(self.thumbs_inner, bg="#f0f0f0")
        frame.grid(row=index, column=0, pady=2, padx=2, sticky="n")
        
        btn = tk.Button(frame, image=tk_img, width=width, height=height, relief=tk.FLAT, bg="#f0f0f0", bd=2)
        btn.pack(side=tk.TOP)
        btn.bind('<ButtonPress-1>', partial(self._on_thumb_press, idx=index))
        btn.bind('<ButtonRelease-1>', partial(self._on_thumb_release, idx=index))
        
        label = tk.Label(frame, text=f"{index+1}", font=("Arial", 10, "bold"), bg="#f0f0f0", fg="#222")
        label.pack(side=tk.TOP, pady=(1,0))
        
        self.thumbnail_buttons[index] = btn
        self.thumbnail_labels[index] = label
        
        if self.selected_page == index:
            self._highlight_selected_thumbnail()


    def _highlight_selected_thumbnail(self):
        for idx, (btn, lbl) in enumerate(zip(self.thumbnail_buttons, self.thumbnail_labels)):
            if btn is None or lbl is None:
                continue
                
            if idx == self.selected_page:
                btn.config(bg="#1976D2", activebackground="#1565C0", bd=3, highlightbackground="#1976D2")
                lbl.config(bg="#1976D2", fg="white")
            else:
                btn.config(bg="#f0f0f0", activebackground="#e0e0e0", bd=2, highlightbackground="#f0f0f0")
                lbl.config(bg="#f0f0f0", fg="#222")

    def _on_thumb_press(self, event, idx):
        self.drag_data['from_idx'] = idx
        self.drag_data['press_y'] = event.y_root
        self.drag_data['moved'] = False
        self.drag_data['target_idx'] = idx
        # Start a timer to detect click if no drag occurs
        if self.drag_data['click_timer']:
            self.after_cancel(self.drag_data['click_timer'])
        self.drag_data['click_timer'] = self.after(200, lambda: None)  # Placeholder, will be canceled if drag
        # Remove any previous highlight line
        if self.drag_data['highlight_line']:
            self.thumb_canvas.delete(self.drag_data['highlight_line'])
            self.drag_data['highlight_line'] = None
        # Bind <B1-Motion> to the root window for global drag tracking
        self.bind('<B1-Motion>', self._on_thumb_motion)

    def _on_thumb_motion(self, event):
        if self.drag_data['from_idx'] is None or self.drag_data['press_y'] is None:
            return
        # Always use current mouse position for y_root
        mouse_y_root = self.winfo_pointery()
        if abs(mouse_y_root - self.drag_data['press_y']) > 8:
            self.drag_data['moved'] = True
            if self.drag_data['click_timer']:
                self.after_cancel(self.drag_data['click_timer'])
                self.drag_data['click_timer'] = None
        # Auto-scroll if near top or bottom of the canvas
        canvas_y = self.thumb_canvas.winfo_rooty()
        canvas_h = self.thumb_canvas.winfo_height()
        mouse_y = mouse_y_root - canvas_y
        scroll_zone = 30  # px
        did_scroll = False
        if mouse_y < scroll_zone:
            self.thumb_canvas.yview_scroll(-1, "units")
            did_scroll = True
        elif mouse_y > canvas_h - scroll_zone:
            self.thumb_canvas.yview_scroll(1, "units")
            did_scroll = True
        if did_scroll:
            self.after(10, lambda e=event: self._on_thumb_motion(e))
            return
        # Map mouse position to scrolled content
        content_y = self.thumb_canvas.canvasy(mouse_y)
        # Calculate the y-positions of the gaps between thumbnails
        gap_positions = [0]
        total = 0
        for j, btn in enumerate(self.thumbnail_buttons):
            # Skip if thumbnail not yet loaded
            if btn is None or self.thumbnail_labels[j] is None:
                continue
                
            h = btn.winfo_height() + self.thumbnail_labels[j].winfo_height() + 3  # 3 for padding
            total += h
            gap_positions.append(total)
        # Find the closest gap to the mouse
        min_dist = float('inf')
        target_gap = None
        for idx, gap_y in enumerate(gap_positions):
            dist = abs(content_y - gap_y)
            if dist < min_dist:
                min_dist = dist
                target_gap = idx
                line_y = gap_y
        # Only show the highlight if the mouse is within 10px of a gap
        if min_dist <= 10:
            self.drag_data['target_idx'] = target_gap
        else:
            self.drag_data['target_idx'] = None
            line_y = None
        # Remove previous highlight line
        if self.drag_data['highlight_line']:
            self.thumb_canvas.delete(self.drag_data['highlight_line'])
            self.drag_data['highlight_line'] = None
        # Draw new highlight line only if near a gap
        if self.drag_data['target_idx'] is not None and line_y is not None:
            self.drag_data['highlight_line'] = self.thumb_canvas.create_line(
                0, line_y, 220, line_y, fill="#1976D2", width=4)

    def _on_thumb_release(self, event, idx):
        if self.drag_data['highlight_line']:
            self.thumb_canvas.delete(self.drag_data['highlight_line'])
            self.drag_data['highlight_line'] = None
        # Unbind the global <B1-Motion> event
        self.unbind('<B1-Motion>')
        # If not moved, treat as click
        if not self.drag_data['moved']:
            self.show_page(idx)
        else:
            # Drag-and-drop logic
            to_idx = self.drag_data['target_idx'] if self.drag_data['target_idx'] is not None else idx
            from_idx = self.drag_data['from_idx']
            if from_idx is not None and to_idx is not None and from_idx != to_idx:
                self._push_undo()
                # Move the page
                self.pdf_doc.move_page(from_idx, to_idx)
                self.refresh_thumbnails()
                # After move, the dragged page will be at:
                # - to_idx-1 if from_idx < to_idx (dragging down)
                # - to_idx if from_idx > to_idx (dragging up)
                if from_idx < to_idx:
                    new_idx = to_idx - 1
                else:
                    new_idx = to_idx
                self.show_page(new_idx)
                self.show_notification("Page reordered.")
        self.drag_data = {'from_idx': None, 'start_y': None, 'press_y': None, 'click_timer': None, 'moved': False, 'highlight_line': None, 'target_idx': None}

    def _ensure_thumbnail_visible(self, index):
        if not self.thumbnail_buttons or index >= len(self.thumbnail_buttons):
            return
            
        try:
            btn = self.thumbnail_buttons[index]
            row_frame = btn.master
             
            # Get coordinates relative to the scrolling frame (thumbs_inner)
            y = row_frame.winfo_y()
            h = row_frame.winfo_height()
            
            total_h = self.thumbs_inner.winfo_height()
            canvas_h = self.thumb_canvas.winfo_height()
            
            if total_h <= canvas_h:
                return # All content fits
                
            # Get visible range in canvas coordinates
            top_visible = self.thumb_canvas.canvasy(0)
            bottom_visible = self.thumb_canvas.canvasy(canvas_h)
            
            # Precision buffer
            margin = 5
            
            # Check if out of view
            if y < (top_visible + margin) or (y + h) > (bottom_visible - margin):
                # Scroll to center the thumbnail
                target_y = max(0, y - (canvas_h / 2) + (h / 2))
                fraction = target_y / total_h
                self.thumb_canvas.yview_moveto(fraction)
        except Exception:
            pass # Avoid errors during layout updates

    def show_page(self, page_index):
        if not self.pdf_doc or page_index < 0 or page_index >= len(self.pdf_doc):
            self.preview_canvas.delete("all")
            self.current_pil_image = None
            # Show drop label when no PDF is loaded
            if not self.pdf_doc:
                self.drop_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
                self._update_path_display()
            return
        # Hide drop label when PDF is loaded
        self.drop_label.place_forget()
        self.selected_page = page_index
        self._highlight_selected_thumbnail()
        self._ensure_thumbnail_visible(page_index)
        # Trigger lazy loading of nearby thumbnails
        if hasattr(self, '_update_thumbnail_window'):
            self._update_thumbnail_window(page_index)
        page = self.pdf_doc[page_index]
        # Render at high resolution, then scale down to fit canvas
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        pil_img = Image.open(io.BytesIO(pix.tobytes("png")))
        self.current_pil_image = pil_img
        self._display_pil_image_on_canvas(pil_img)
        # Update page label
        if hasattr(self, 'page_label') and self.pdf_doc:
            self.page_label.configure(text=f"Page {self.selected_page+1} / {len(self.pdf_doc)}")

    def _display_pil_image_on_canvas(self, pil_img):
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        if canvas_width < 10 or canvas_height < 10:
            return
        # Fit image to canvas, maintain aspect ratio
        img_w, img_h = pil_img.size
        scale = min(canvas_width / img_w, canvas_height / img_h)
        new_w = int(img_w * scale)
        new_h = int(img_h * scale)
        resized_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
        tk_img = ImageTk.PhotoImage(resized_img)
        self.preview_canvas.delete("all")
        self.preview_canvas.image = tk_img
        self.preview_canvas.create_image((canvas_width - new_w)//2, (canvas_height - new_h)//2, anchor="nw", image=tk_img)

    def insert_page(self):
        if not self.pdf_doc:
            messagebox.showwarning("No PDF", "Open a PDF first.")
            return
        if self.selected_page is None:
            messagebox.showwarning("No Selection", "Select a page to insert before/after.")
            return
        # Ask user to select another PDF file first
        path = filedialog.askopenfilename(filetypes=[("PDF Files", "*.pdf")])
        if not path:
            return
        # Custom dialog for Before/After
        def on_choice(choice):
            dialog.destroy()
            self._insert_pdf_at_position(before=(choice == 'before'), pdf_path=path)
        dialog = tk.Toplevel(self)
        dialog.title("Insert Page")
        dialog.geometry("260x120")
        dialog.grab_set()
        label = tk.Label(dialog, text="Insert the selected PDF before or after the current page?", font=("Arial", 11))
        label.pack(pady=15, padx=10)
        btn_frame = tk.Frame(dialog)
        btn_frame.pack(pady=5)
        before_btn = tk.Button(btn_frame, text="Before", width=10, command=lambda: on_choice('before'))
        before_btn.pack(side=tk.LEFT, padx=10)
        after_btn = tk.Button(btn_frame, text="After", width=10, command=lambda: on_choice('after'))
        after_btn.pack(side=tk.LEFT, padx=10)
        dialog.transient(self)
        dialog.wait_window()

    def delete_page(self):
        if not self.pdf_doc:
            messagebox.showwarning("No PDF", "Open a PDF first.")
            return
        idx = self.selected_page if self.selected_page is not None else 0
        if len(self.pdf_doc) == 1:
            messagebox.showwarning("Cannot Delete", "A PDF must have at least one page.")
            return
        self._push_undo()
        self.pdf_doc.delete_page(idx)
        self.refresh_thumbnails()
        self.show_page(min(idx, len(self.pdf_doc)-1))
        self.show_notification("Page deleted.")

    def delete_multiple_pages(self):
        if not self.pdf_doc:
            messagebox.showwarning("No PDF", "Open a PDF first.")
            return
        # Prompt for input
        input_dialog = tk.Toplevel(self)
        input_dialog.title("Delete Multiple Pages")
        input_dialog.geometry("350x150")
        input_dialog.grab_set()
        label = tk.Label(input_dialog, text="Enter page numbers or ranges (e.g. 1,7,8 or 5-9):", font=("Arial", 11))
        label.pack(pady=10, padx=10)
        entry = tk.Entry(input_dialog, font=("Arial", 12))
        entry.pack(pady=5, padx=10, fill=tk.X)
        entry.focus_set()
        def on_delete():
            raw = entry.get().replace(' ', '')
            if not raw:
                messagebox.showwarning("Input Required", "Please enter page numbers or ranges.", parent=input_dialog)
                return
            try:
                pages_to_delete = set()
                for part in raw.split(','):
                    if '-' in part:
                        start, end = part.split('-')
                        start, end = int(start), int(end)
                        if start > end:
                            raise ValueError
                        pages_to_delete.update(range(start, end+1))
                    else:
                        pages_to_delete.add(int(part))
                # Convert to zero-based and sort descending for safe deletion
                pages_to_delete = sorted([p-1 for p in pages_to_delete if 1 <= p <= len(self.pdf_doc)], reverse=True)
                if not pages_to_delete:
                    raise ValueError
                for p in pages_to_delete:
                    if 0 <= p < len(self.pdf_doc):
                        self.pdf_doc.delete_page(p)
                input_dialog.destroy()
                self.refresh_thumbnails()
                self.show_page(0)
            except Exception:
                messagebox.showerror("Error", "Invalid input. Use e.g. 1,7,8 or 5-9.", parent=input_dialog)
        delete_btn = tk.Button(input_dialog, text="Delete", command=on_delete, width=10)
        delete_btn.pack(pady=10)
        input_dialog.transient(self)
        input_dialog.wait_window()

    def reorder_pages(self):
        messagebox.showinfo("Info", "You can now drag and drop thumbnails to reorder pages.")

    def insert_before(self):
        self._insert_pdf_at_position(before=True)

    def insert_after(self):
        self._insert_pdf_at_position(before=False)

    def _insert_pdf_at_position(self, before=True, pdf_path=None):
        if not self.pdf_doc or pdf_path is None:
            return
        if self.selected_page is None:
            return
        insert_at = self.selected_page if before else self.selected_page + 1
        try:
            self._push_undo()
            ext_pdf = fitz.open(pdf_path)
            for i in range(len(ext_pdf)):
                self.pdf_doc.insert_pdf(ext_pdf, from_page=i, to_page=i, start_at=insert_at + i)
            ext_pdf.close()
            self.refresh_thumbnails()
            self.show_page(insert_at)
            self._update_undo_redo_btn_state()
            self.show_notification("Page(s) inserted.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to insert PDF pages: {e}")

    def merge_pdfs(self):
        paths = list(filedialog.askopenfilenames(
            title="Select PDFs to Merge",
            filetypes=[("PDF Files", "*.pdf")],
            multiple=True
        ))
        if not paths:
            self.show_notification("No PDF selected.")
            return
        # Modal dialog for reordering and adding/removing
        dialog = tk.Toplevel(self)
        dialog.title("Reorder PDFs to Merge")
        dialog.geometry("420x480")
        dialog.grab_set()
        dialog.configure(bg="#222831")
        tk.Label(dialog, text="Reorder PDFs (top = first in merged)", font=("Arial", 12, "bold"), bg="#222831", fg="#eeeeee").pack(pady=10)
        listbox = tk.Listbox(dialog, selectmode=tk.SINGLE, font=("Arial", 11), bg="#393e46", fg="#eeeeee", selectbackground="#1976D2", selectforeground="#fff", highlightbackground="#222831", highlightcolor="#1976D2", relief=tk.FLAT)
        for p in paths:
            listbox.insert(tk.END, os.path.basename(p))
        listbox.pack(fill=tk.BOTH, expand=True, padx=20, pady=10)
        # Up/Down/Add/Remove buttons
        btn_frame = tk.Frame(dialog)
        btn_frame.configure(bg="#222831")
        btn_frame.pack(pady=5)
        def move_up():
            sel = listbox.curselection()
            if not sel or sel[0] == 0:
                return
            idx = sel[0]
            item = listbox.get(idx)
            item_path = paths[idx]
            listbox.delete(idx)
            listbox.insert(idx-1, item)
            listbox.selection_set(idx-1)
            # Move path in paths list
            paths.insert(idx-1, paths.pop(idx))
        def move_down():
            sel = listbox.curselection()
            if not sel or sel[0] == listbox.size()-1:
                return
            idx = sel[0]
            item = listbox.get(idx)
            item_path = paths[idx]
            listbox.delete(idx)
            listbox.insert(idx+1, item)
            listbox.selection_set(idx+1)
            # Move path in paths list
            paths.insert(idx+1, paths.pop(idx))
        def add_pdf():
            new_paths = list(filedialog.askopenfilenames(
                title="Add PDFs to Merge",
                filetypes=[("PDF Files", "*.pdf")],
                multiple=True
            ))
            for p in new_paths:
                if p not in paths:
                    paths.append(p)
                    listbox.insert(tk.END, os.path.basename(p))
        def remove_pdf():
            sel = listbox.curselection()
            if not sel:
                return
            idx = sel[0]
            listbox.delete(idx)
            paths.pop(idx)
        btn_style = {"bg": "#393e46", "fg": "#eeeeee", "activebackground": "#1976D2", "activeforeground": "#fff", "relief": tk.FLAT, "font": ("Arial", 10, "bold")}
        up_btn = tk.Button(btn_frame, text="Up", width=8, command=move_up, **btn_style)
        up_btn.pack(side=tk.LEFT, padx=5)
        down_btn = tk.Button(btn_frame, text="Down", width=8, command=move_down, **btn_style)
        down_btn.pack(side=tk.LEFT, padx=5)
        add_btn = tk.Button(btn_frame, text="Add PDF", width=10, command=add_pdf, **btn_style)
        add_btn.pack(side=tk.LEFT, padx=5)
        remove_btn = tk.Button(btn_frame, text="Remove", width=10, command=remove_pdf, **btn_style)
        remove_btn.pack(side=tk.LEFT, padx=5)
        # Merge Now button
        def do_merge():
            if len(paths) < 2:
                self.show_notification("Select at least two PDFs to merge.")
                return
            import fitz, tempfile, uuid, os
            merged_pdf = fitz.open()
            try:
                for pdf_path in paths:
                    src = fitz.open(pdf_path)
                    merged_pdf.insert_pdf(src)
                    src.close()
                # Save to a temp file and open in editor
                temp_dir = tempfile.gettempdir()
                temp_path = os.path.join(temp_dir, f"merged_{uuid.uuid4().hex}.pdf")
                merged_pdf.save(temp_path)
                self.show_notification("PDFs merged and loaded in editor!")
                self.open_pdf(temp_path, is_merged=True)
            except Exception as e:
                self.show_notification(f"Merge failed: {e}")
            finally:
                merged_pdf.close()
            dialog.destroy()
        merge_btn = tk.Button(dialog, text="Merge Now", font=("Arial", 12, "bold"), command=do_merge, bg="#1976D2", fg="#fff", activebackground="#1565C0", activeforeground="#fff", relief=tk.FLAT)
        merge_btn.pack(pady=15)
        dialog.transient(self)
        dialog.wait_window()

    def rotate_page(self):
        if not self.pdf_doc or self.selected_page is None:
            self.show_notification("No page selected to rotate.")
            return
        self._push_undo()
        page = self.pdf_doc[self.selected_page]
        page.set_rotation((page.rotation + 90) % 360)
        self.refresh_thumbnails()
        self.show_page(self.selected_page)
        self.show_notification("Page rotated 90° clockwise.")

    def compress_pdf(self):
        if not self.pdf_doc or not self.pdf_path:
            messagebox.showwarning("No PDF", "Open a PDF first.")
            return
        
        # Show compression options dialog
        dialog = tk.Toplevel(self)
        dialog.title("Compress PDF")
        dialog.geometry("400x300")
        dialog.grab_set()
        dialog.transient(self)
        
        # Method selection
        method_var = tk.StringVar(value="quality")
        
        def toggle_inputs():
            if method_var.get() == "quality":
                quality_frame.pack(fill=tk.X, padx=20, pady=5)
                target_frame.pack_forget()
            else:
                quality_frame.pack_forget()
                target_frame.pack(fill=tk.X, padx=20, pady=5)
        
        tk.Label(dialog, text="Compression Method:", font=("Arial", 12, "bold")).pack(pady=(15, 5))
        tk.Radiobutton(dialog, text="Preset Quality", variable=method_var, value="quality", command=toggle_inputs, font=("Arial", 11)).pack(anchor="w", padx=40)
        tk.Radiobutton(dialog, text="Target File Size", variable=method_var, value="target", command=toggle_inputs, font=("Arial", 11)).pack(anchor="w", padx=40)
        
        # Quality Inputs
        quality_frame = tk.Frame(dialog)
        tk.Label(quality_frame, text="Select Quality:", font=("Arial", 11)).pack(anchor="w")
        quality_var = tk.StringVar(value="medium")
        tk.Radiobutton(quality_frame, text="High (Low Compression)", variable=quality_var, value="high").pack(anchor="w", padx=10)
        tk.Radiobutton(quality_frame, text="Medium (Balanced)", variable=quality_var, value="medium").pack(anchor="w", padx=10)
        tk.Radiobutton(quality_frame, text="Low (Max Compression)", variable=quality_var, value="low").pack(anchor="w", padx=10)
        
        # Target Size Inputs
        target_frame = tk.Frame(dialog)
        tk.Label(target_frame, text="Target Size (MB):", font=("Arial", 11)).pack(anchor="w")
        target_entry = tk.Entry(target_frame, font=("Arial", 12))
        target_entry.pack(fill=tk.X, padx=10, pady=5)
        
        toggle_inputs() # Initialize state
        
        result = {'process': False}
        def on_compress():
            result['process'] = True
            result['method'] = method_var.get()
            result['quality'] = quality_var.get()
            result['target'] = target_entry.get()
            dialog.destroy()
            
        tk.Button(dialog, text="Compress Now", command=on_compress, bg="#1976D2", fg="white", font=("Arial", 11, "bold")).pack(pady=20)
        
        dialog.wait_window()
        
        if not result['process']:
            return
            
        # Get output path
        output_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=f"compressed_{os.path.basename(self.pdf_path)}"
        )
        if not output_path:
            return
            
        # Progress UI
        progress_win = tk.Toplevel(self)
        progress_win.title("Processing")
        progress_win.geometry("300x100")
        progress_win.transient(self)
        progress_win.grab_set()
        tk.Label(progress_win, text="Compressing PDF...", font=("Arial", 12)).pack(expand=True)
        progress_win.update()
        
        try:
            target_mb = None
            if result['method'] == 'target':
                try:
                    target_mb = float(result['target'])
                except ValueError:
                    messagebox.showerror("Error", "Invalid target size.")
                    progress_win.destroy()
                    return

            # Perform compression
            final_size = self._compress_pdf_logic(output_path, result['quality'], target_mb)
            
            progress_win.destroy()
            
            # Show result
            size_msg = f"Final Size: {final_size/1024/1024:.2f} MB"
            if target_mb and final_size > target_mb * 1024 * 1024:
                size_msg += f"\n(Could not reach target {target_mb} MB)"
            
            messagebox.showinfo("Success", f"Compression Complete!\n{size_msg}")
            
            # Ask to open
            if messagebox.askyesno("Open", "Open compressed file?"):
                self.open_pdf(output_path)
                
        except Exception as e:
            progress_win.destroy()
            messagebox.showerror("Error", f"Compression failed: {e}")

    def _compress_pdf_logic(self, output_path, quality_preset, target_mb=None):
        import fitz
        
        # Levels: (DPI, JPEG Quality)
        presets = {
            'high': (150, 85),
            'medium': (96, 70),
            'low': (72, 50)
        }
        
        # If target size is set, we iterate starting from medium
        if target_mb:
            target_bytes = target_mb * 1024 * 1024
            original_size = os.path.getsize(self.pdf_path)
            
            if original_size <= target_bytes:
                # Just deflate and save
                self.pdf_doc.save(output_path, garbage=4, deflate=True)
                return os.path.getsize(output_path)
                
            # Try progressively aggressive compression
            attempts = [
                (150, 75), # Attempt 1
                (96, 60),  # Attempt 2
                (72, 40),  # Attempt 3
                (50, 30)   # Attempt 4 (Desperate)
            ]
            
            for i, (dpi, jpg_q) in enumerate(attempts):
                # We need to work on a copy to avoid messing up the current open doc interface
                # or just process images and undo? Safer to open a fresh handle or copy.
                # Since self.pdf_doc is open, let's save to a temp path then process.
                
                # For simplicity in this app structure, we will save to output_path and check size
                # To do that we need to iterate images.
                
                # Optimized approach: use `cpdf` or `ghostscript` is better but we promised pure python/pymupdf
                # PyMuPDF doesn't have a simple "save with global downsample" flag yet.
                # We must iterate pages and images.
                
                # Make a temporary copy of the doc for processing
                temp_doc = fitz.open(self.pdf_path)
                self._downsample_images(temp_doc, dpi, jpg_q)
                temp_doc.save(output_path, garbage=4, deflate=True)
                temp_doc.close()
                
                current_size = os.path.getsize(output_path)
                if current_size <= target_bytes:
                    return current_size
            
            return os.path.getsize(output_path) # Return best effort
            
        else:
            # Preset mode
            dpi, jpg_q = presets.get(quality_preset, (96, 75))
            temp_doc = fitz.open(self.pdf_path)
            self._downsample_images(temp_doc, dpi, jpg_q)
            temp_doc.save(output_path, garbage=4, deflate=True)
            temp_doc.close()
            return os.path.getsize(output_path)

    def _downsample_images(self, doc, target_dpi, jpeg_quality):
        import fitz
        
        xrefs = set()
        for page in doc:
            for img in page.get_images():
                xref = img[0]
                if xref in xrefs:
                    continue
                xrefs.add(xref)
                
                # Determine if image needs downsampling
                # We can't easily get DPI, but we can get dimensions
                # A heuristic: check image width/height vs page width/height is complex without location.
                # Simple heuristic: if width > 2000, likely high res.
                
                # Actually, PyMuPDF allows updating the image stream.
                try:
                    pix = fitz.Pixmap(doc, xref)
                    
                    # Skip small images (icons, logos)
                    if pix.width < 100 or pix.height < 100:
                        continue
                        
                    # Calculate scaling
                    # This is rough because we don't know the physical size of the image on the page
                    # But for general compression, reducing pixel count is key.
                    # We'll limit max dimension.
                    
                    # Assuming 8.27 inch width (A4) * target_dpi
                    max_dim = int(8.27 * target_dpi * 1.5) # *1.5 Slack
                    
                    if pix.width > max_dim or pix.height > max_dim:
                        # Downscale
                        scale = min(max_dim/pix.width, max_dim/pix.height)
                        new_w = int(pix.width * scale)
                        new_h = int(pix.height * scale)
                        
                        # fitz.Pixmap(colorspace, rect, alpha) - resizing needs care
                        # Easiest: use PIL
                        img_data = pix.tobytes()
                        from PIL import Image
                        import io
                        
                        with Image.open(io.BytesIO(img_data)) as pil_img:
                            pil_img = pil_img.resize((new_w, new_h), Image.LANCZOS)
                            
                            # Convert back to bytes (JPEG)
                            out_buffer = io.BytesIO()
                            pil_img = pil_img.convert("RGB") # Ensure no alpha for JPEG
                            pil_img.save(out_buffer, format="JPEG", quality=jpeg_quality, optimize=True)
                            new_data = out_buffer.getvalue()
                            
                            doc.update_stream(xref, new_data)
                except Exception:
                    pass # Skip errors on individual images
                




    def convert_page(self):
        if not self.pdf_doc or self.selected_page is None:
            messagebox.showwarning("No Page Selected", "Select a PDF page to convert.")
            return
        # Prompt for format
        dialog = tk.Toplevel(self)
        dialog.title("Convert Page")
        dialog.geometry("300x200")
        dialog.grab_set()
        tk.Label(dialog, text="Select output format:", font=("Arial", 12)).pack(pady=15)
        var = tk.StringVar(value="PNG")
        formats = ["PNG", "JPG", "DOCX"]
        for fmt in formats:
            tk.Radiobutton(dialog, text=fmt, variable=var, value=fmt, font=("Arial", 11)).pack(anchor="w", padx=40)
        def on_ok():
            dialog.destroy()
        ok_btn = tk.Button(dialog, text="OK", command=on_ok, width=10)
        ok_btn.pack(pady=15)
        dialog.transient(self)
        dialog.wait_window()
        fmt = var.get()
        # Save As dialog
        filetypes = []
        ext = fmt.lower()
        if fmt == "PNG":
            filetypes = [("PNG Image", "*.png")]
        elif fmt == "JPG":
            filetypes = [("JPEG Image", "*.jpg;*.jpeg")]
        elif fmt == "DOCX":
            filetypes = [("Word Document", "*.docx")]
        else:
            return
        path = filedialog.asksaveasfilename(defaultextension=f".{ext}", filetypes=filetypes)
        if not path:
            return
        try:
            page = self.pdf_doc[self.selected_page]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            if fmt in ("PNG", "JPG"):
                # Save as image
                save_fmt = "JPEG" if fmt == "JPG" else fmt
                img.save(path, save_fmt)
                self.show_notification(f"Page saved as {fmt}.")
            elif fmt == "DOCX":
                try:
                    from docx import Document
                    from docx.shared import Inches
                except ImportError:
                    messagebox.showerror("Missing Dependency", "Please install python-docx to export as DOCX.")
                    return
                doc = Document()
                # Save image to temp file
                import tempfile
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp_img:
                    img.save(tmp_img.name, "PNG")
                    doc.add_picture(tmp_img.name, width=Inches(6))
                doc.save(path)
                self.show_notification("Page saved as DOCX (image in Word doc).")
            else:
                messagebox.showerror("Error", "Unsupported format.")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to convert page: {e}")

    def on_close(self):
        # Clean up temp file if it exists
        if self.pdf_doc:
            try:
                self.pdf_doc.close()
            except Exception:
                pass
        if self.pdf_temp_path and os.path.exists(self.pdf_temp_path):
            try:
                os.remove(self.pdf_temp_path)
            except Exception:
                pass
        self.destroy()

    def _on_arrow_key(self, event):
        if not self.pdf_doc or self.selected_page is None:
            return
        if event.keysym in ('Right', 'Down'):
            if self.selected_page < len(self.pdf_doc) - 1:
                self.show_page(self.selected_page + 1)
        elif event.keysym in ('Left', 'Up'):
            if self.selected_page > 0:
                self.show_page(self.selected_page - 1)

    def _push_undo(self):
        if self.pdf_doc:
            try:
                self.undo_stack.append(self.pdf_doc.write())
                if len(self.undo_stack) > 10:
                    self.undo_stack.pop(0)
                self.redo_stack.clear()
                self._update_undo_redo_btn_state()
            except Exception:
                pass

    def undo(self):
        if not self.undo_stack:
            return
        try:
            self.redo_stack.append(self.pdf_doc.write())
            if len(self.redo_stack) > 10:
                self.redo_stack.pop(0)
            prev_state = self.undo_stack.pop()
            self.pdf_doc = fitz.open(stream=prev_state, filetype='pdf')
            self.refresh_thumbnails()
            self.show_page(0)
            self._update_undo_redo_btn_state()
            self.show_notification("Undo.")
        except Exception:
            messagebox.showerror("Undo Error", "Failed to undo.")

    def redo(self):
        if not self.redo_stack:
            return
        try:
            self.undo_stack.append(self.pdf_doc.write())
            if len(self.undo_stack) > 10:
                self.undo_stack.pop(0)
            next_state = self.redo_stack.pop()
            self.pdf_doc = fitz.open(stream=next_state, filetype='pdf')
            self.refresh_thumbnails()
            self.show_page(0)
            self._update_undo_redo_btn_state()
            self.show_notification("Redo.")
        except Exception:
            messagebox.showerror("Redo Error", "Failed to redo.")

    def _on_undo(self, event=None):
        self.undo()

    def _on_redo(self, event=None):
        self.redo()

    def _update_undo_redo_btn_state(self):
        pass

    def show_notification(self, message, duration=1500):
        # Floating, top-right, borderless notification
        notif = tk.Toplevel(self)
        notif.overrideredirect(True)
        notif.attributes("-topmost", True)
        notif.configure(bg="#1976D2")
        label = tk.Label(notif, text=message, font=("Arial", 14, "bold"), bg="#1976D2", fg="white", padx=30, pady=15)
        label.pack()
        notif.update_idletasks()
        # Place the notification in the top right corner with a margin
        margin_x = 30
        margin_y = 30
        x = self.winfo_rootx() + self.winfo_width() - notif.winfo_width() - margin_x
        y = self.winfo_rooty() + margin_y
        notif.geometry(f"+{x}+{y}")
        notif.after(duration, notif.destroy)

    def _update_save_btn_state(self):
        if hasattr(self, 'save_over_btn'):
            if self.is_merged_pdf:
                self.save_over_btn.configure(state="disabled")
            else:
                self.save_over_btn.configure(state="normal")

    def show_about(self):
        about_text = (
            "PDF Editor\n"
            "\u00A9 JR-Contract Cell\n"
            "All rights reserved."
        )
        tk.messagebox.showinfo("About PDF Editor", about_text)

    def _goto_page(self):
        if not self.pdf_doc:
            return
        try:
            page_num = int(self.goto_entry.get())
            if 1 <= page_num <= len(self.pdf_doc):
                self.show_page(page_num - 1)
            else:
                self.show_notification(f"Page must be 1 to {len(self.pdf_doc)}")
        except Exception:
            self.show_notification("Enter a valid page number")

    def _setup_drag_drop(self):
        """
        Sets up native drag and drop for PDF files.
        This function is platform-specific and requires a different implementation
        for different operating systems.
        """
        if DRAG_DROP_AVAILABLE:
            # Enable drag and drop on the main window
            self.drop_target_register(DND_FILES)
            self.dnd_bind('<<Drop>>', self._on_drop_pdf)
            
            # Enable drag and drop on the preview canvas
            self.preview_canvas.drop_target_register(DND_FILES)
            self.preview_canvas.dnd_bind('<<Drop>>', self._on_drop_pdf)
            
            # Add visual feedback for drag and drop
            self.preview_canvas.bind('<Enter>', self._on_drag_enter)
            self.preview_canvas.bind('<Leave>', self._on_drag_leave)
            
            # Add a drop zone label for visual feedback
            self.drop_label = tk.Label(self.preview_canvas, 
                                      text="📄 Drop PDF files here\nor click to open", 
                                      font=("Arial", 16, "bold"), 
                                      bg="#23272e", fg="#666666",
                                      justify=tk.CENTER,
                                      cursor="hand2")
            self.drop_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            
            # Bind click events to open file dialog
            self.drop_label.bind('<Button-1>', self._on_drop_zone_click)
            self.drop_label.bind('<Enter>', self._on_drop_zone_enter)
            self.drop_label.bind('<Leave>', self._on_drop_zone_leave)
            
            # Also bind to the canvas for larger click area
            self.preview_canvas.bind('<Button-1>', self._on_canvas_click)
        else:
            # Fallback for when tkinterdnd2 is not available
            self.drop_label = tk.Label(self.preview_canvas, 
                                      text="📄 Click here to open PDF\n(tkinterdnd2 not available for drag & drop)", 
                                      font=("Arial", 16, "bold"), 
                                      bg="#23272e", fg="#666666",
                                      justify=tk.CENTER,
                                      cursor="hand2")
            self.drop_label.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
            
            # Bind click events to open file dialog
            self.drop_label.bind('<Button-1>', self._on_drop_zone_click)
            self.drop_label.bind('<Enter>', self._on_drop_zone_enter)
            self.drop_label.bind('<Leave>', self._on_drop_zone_leave)
            
            # Also bind to the canvas for larger click area
            self.preview_canvas.bind('<Button-1>', self._on_canvas_click)

    def _on_drop_pdf(self, event):
        """Handle PDF file drop events"""
        if DRAG_DROP_AVAILABLE:
            # Get the dropped file path
            file_path = event.data
            
            # Clean up the file path (remove braces and quotes)
            if file_path.startswith('{') and file_path.endswith('}'):
                file_path = file_path[1:-1]
            if file_path.startswith('"') and file_path.endswith('"'):
                file_path = file_path[1:-1]
            
            # Handle multiple files (take the first PDF)
            if file_path.startswith('(') and file_path.endswith(')'):
                files = file_path[1:-1].split(') (')
                for f in files:
                    if f.lower().endswith('.pdf'):
                        file_path = f
                        break
            
            # Check if it's a PDF file
            if file_path.lower().endswith('.pdf'):
                if os.path.exists(file_path):
                    self.open_pdf(file_path)
                    self.show_notification(f"Opened: {os.path.basename(file_path)}")
                else:
                    self.show_notification("File not found.")
            else:
                self.show_notification("Please drop a PDF file.")
        else:
            # Fallback to file dialog
            self.open_pdf()

    def _on_drag_enter(self, event):
        """Visual feedback when dragging over the drop zone"""
        if DRAG_DROP_AVAILABLE and not self.pdf_doc:
            # Don't change canvas color, just change the drop label
            if hasattr(self, 'drop_label'):
                self.drop_label.configure(bg="#1976D2", fg="white")

    def _on_drag_leave(self, event):
        """Restore appearance when leaving drop zone"""
        if DRAG_DROP_AVAILABLE and not self.pdf_doc:
            # Keep canvas color unchanged, just restore drop label
            if hasattr(self, 'drop_label'):
                self.drop_label.configure(bg="#23272e", fg="#666666")

    def _on_drag_over(self, event):
        pass

    def _on_drag_leave(self, event):
        pass
        
    def _on_drop_zone_click(self, event):
        """Open file dialog when clicking on the drop zone"""
        if not self.pdf_doc:  # Only if no PDF is currently open
            self.open_pdf()
            
    def _on_drop_zone_enter(self, event):
        """Change appearance when hovering over drop zone"""
        if not self.pdf_doc:
            self.drop_label.configure(fg="#1976D2", font=("Arial", 16, "bold"))
            
    def _on_drop_zone_leave(self, event):
        """Restore appearance when leaving drop zone"""
        if not self.pdf_doc:
            self.drop_label.configure(fg="#666666", font=("Arial", 16, "bold"))
            
    def _on_canvas_click(self, event):
        """Open file dialog when clicking on empty canvas area"""
        if not self.pdf_doc:  # Only if no PDF is currently open
            self.open_pdf()
            
    def _open_pdf_folder(self, event):
        """Open the folder containing the currently opened PDF file"""
        if self.pdf_path:
            folder_path = os.path.dirname(self.pdf_path)
            if os.path.exists(folder_path):
                os.startfile(folder_path)
            else:
                messagebox.showwarning("Folder Not Found", f"Folder '{folder_path}' not found.")
        else:
            messagebox.showinfo("No PDF", "No PDF file is currently opened.")

    def _update_path_display(self):
        """Update the path display label with the current PDF path"""
        if self.pdf_path:
            # Show the full path, but truncate if too long
            full_path = self.pdf_path
            if len(full_path) > 80:
                # Truncate to show beginning and end
                start = full_path[:40]
                end = full_path[-35:]
                display_path = f"{start}...{end}"
            else:
                display_path = full_path
            self.path_label.configure(text=display_path, text_color="#ffffff")
        else:
            self.path_label.configure(text="No PDF opened", text_color="#cccccc")


if __name__ == "__main__":
    app = PDFEditorApp()
    app.mainloop() 