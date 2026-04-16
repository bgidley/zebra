VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "Dialog"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = True
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit

Implements IDialog
Private dlg As MSComDlg.CommonDialog
Public Sub init(frm As frmMDI)
    Set dlg = frm.dlg
End Sub

Private Property Let IDialog_dialogTitle(RHS As String)
    dlg.DialogTitle = RHS
End Property

Private Property Get IDialog_dialogTitle() As String
    IDialog_dialogTitle = dlg.DialogTitle
End Property

Private Property Let IDialog_fileName(RHS As String)
    dlg.fileName = RHS
End Property

Private Property Get IDialog_fileName() As String
    IDialog_fileName = dlg.fileName
End Property

Private Property Let IDialog_filter(RHS As String)
    dlg.Filter = RHS
End Property

Private Property Get IDialog_filter() As String
    IDialog_filter = dlg.Filter
End Property

Private Property Let IDialog_filterIndex(RHS As Integer)
    dlg.FilterIndex = RHS
End Property

Private Property Get IDialog_filterIndex() As Integer
    IDialog_filterIndex = dlg.FilterIndex
End Property

Private Function IDialog_ShowSave() As Boolean
    On Error Resume Next
    dlg.Flags = cdlOFNOverwritePrompt
    dlg.ShowSave
    IDialog_ShowSave = Err.Number = 0
End Function
