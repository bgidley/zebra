VERSION 1.0 CLASS
BEGIN
  MultiUse = -1  'True
  Persistable = 0  'NotPersistable
  DataBindingBehavior = 0  'vbNone
  DataSourceBehavior  = 0  'vbNone
  MTSTransactionMode  = 0  'NotAnMTSObject
END
Attribute VB_Name = "AddinAccess"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = False
Attribute VB_Exposed = False
Option Explicit
Private mMDI As frmMDI
Private mDialog As Dialog
Implements IAddinAccess
Public Sub init(frm As frmMDI)
    Set mMDI = frm
    Set mDialog = New Dialog
    mDialog.init frm
End Sub
Public Property Get IAddinAccess_dialog() As IDialog
    Set IAddinAccess_dialog = mDialog
End Property

Public Property Get IAddinAccess_activeProcessDef() As ProcessDef
    Set IAddinAccess_activeProcessDef = mMDI.activeProcessDef
End Property

Public Sub IAddinAccess_refreshProcessDisplay()
    mMDI.refreshActiveProcess
End Sub

Private Property Get IAddinAccess_TemplatePath() As String
    IAddinAccess_TemplatePath = validatepath(Left$(mMDI.getTemplatePath(), InStr(mMDI.getTemplatePath(), "\Templates")))
End Property
