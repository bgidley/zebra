VERSION 5.00
Begin VB.Form frmTextPopup 
   BorderStyle     =   3  'Fixed Dialog
   Caption         =   "Editing Property..."
   ClientHeight    =   3195
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   4680
   ControlBox      =   0   'False
   BeginProperty Font 
      Name            =   "Tahoma"
      Size            =   8.25
      Charset         =   0
      Weight          =   400
      Underline       =   0   'False
      Italic          =   0   'False
      Strikethrough   =   0   'False
   EndProperty
   MaxButton       =   0   'False
   MinButton       =   0   'False
   ScaleHeight     =   3195
   ScaleWidth      =   4680
   ShowInTaskbar   =   0   'False
   StartUpPosition =   1  'CenterOwner
   Begin VB.CommandButton cmdCancel 
      Cancel          =   -1  'True
      Caption         =   "Cancel"
      Height          =   495
      Left            =   3300
      TabIndex        =   2
      Top             =   2580
      Width           =   1215
   End
   Begin VB.CommandButton cmdOK 
      Caption         =   "OK"
      Height          =   495
      Left            =   120
      TabIndex        =   1
      Top             =   2580
      Width           =   1215
   End
   Begin VB.TextBox txt 
      Height          =   2355
      Left            =   120
      MultiLine       =   -1  'True
      TabIndex        =   0
      Text            =   "frmTextPopup.frx":0000
      Top             =   120
      Width           =   4395
   End
End
Attribute VB_Name = "frmTextPopup"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
Option Explicit
Private mfCancel As Boolean
Public Property Get Text() As String
    Text = txt.Text
End Property
Public Function doTextPopup(oProperty As Property) As Boolean
    txt.Text = oProperty.Value
    txt.SelStart = 0
    txt.SelLength = Len(txt.Text)
    Me.Caption = "Editing " & oProperty.Name
    Me.Show vbModal, frmMDI
    doTextPopup = Not mfCancel
End Function

Private Sub cmdCancel_Click()
    mfCancel = True
    Me.Hide
End Sub

Private Sub cmdOK_Click()
    mfCancel = False
    Me.Hide
End Sub

