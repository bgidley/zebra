VERSION 5.00
Begin VB.Form frmPropertyAdd 
   BorderStyle     =   3  'Fixed Dialog
   Caption         =   "Add Property"
   ClientHeight    =   1635
   ClientLeft      =   45
   ClientTop       =   330
   ClientWidth     =   3495
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
   ScaleHeight     =   1635
   ScaleWidth      =   3495
   ShowInTaskbar   =   0   'False
   StartUpPosition =   3  'Windows Default
   Visible         =   0   'False
   Begin VB.TextBox txtPropName 
      Height          =   315
      Left            =   120
      TabIndex        =   1
      Top             =   540
      Width           =   3255
   End
   Begin VB.ComboBox cboPropGroup 
      Height          =   315
      Left            =   120
      Sorted          =   -1  'True
      Style           =   2  'Dropdown List
      TabIndex        =   0
      Top             =   120
      Width           =   3255
   End
   Begin VB.CommandButton cmdOK 
      Caption         =   "OK"
      Height          =   495
      Left            =   120
      TabIndex        =   3
      Top             =   1020
      Width           =   1215
   End
   Begin VB.CommandButton cmdCancel 
      Cancel          =   -1  'True
      Caption         =   "Cancel"
      Height          =   495
      Left            =   2160
      TabIndex        =   2
      Top             =   1020
      Width           =   1215
   End
End
Attribute VB_Name = "frmPropertyAdd"
Attribute VB_GlobalNameSpace = False
Attribute VB_Creatable = False
Attribute VB_PredeclaredId = True
Attribute VB_Exposed = False
'/*
' * Copyright 2004 Anite - Central Government Division
' *    http://www.anite.com/publicsector
' *
' * Licensed under the Apache License, Version 2.0 (the "License");
' * you may not use this file except in compliance with the License.
' * You may obtain a copy of the License at
' *
' *    http://www.apache.org/licenses/LICENSE-2.0
' *
' * Unless required by applicable law or agreed to in writing, software
' * distributed under the License is distributed on an "AS IS" BASIS,
' * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
' * See the License for the specific language governing permissions and
' * limitations under the License.
' */
Option Explicit
Private mfCancel As Boolean
Private moPropWin As frmPropList
Public Function AddProp(oPropWin As frmPropList)
    Dim oProps As Properties
    On Error GoTo Err_Handler
    Set moPropWin = oPropWin
    For Each oProps In oPropWin.pg.PropertyGroup
        'If oProps.Name <> "(General)" Then
            cboPropGroup.AddItem oProps.Name
        'End If
    Next
    cboPropGroup.ListIndex = 0
    Me.Show vbModal
    If Not mfCancel Then
        moPropWin.pg.Refresh
    End If
    Set moPropWin = Nothing
    AddProp = mfCancel
    Exit Function
Err_Handler:
    Exit Function
End Function

Private Sub cmdCancel_Click()
    mfCancel = True
    Me.Hide
End Sub

Private Sub cmdOK_Click()
    Dim oPG As PropertyGroup
    Set oPG = moPropWin.pg.PropertyGroup
    Dim oProps As Properties
    Dim strNewProp As String
    strNewProp = Trim$(txtPropName.Text)
    If Len(strNewProp) = 0 Then Exit Sub
    
    Set oProps = oPG(cboPropGroup.Text)
    
    If oProps.Exists(strNewProp) Then
        MsgBox "A Property named " & strNewProp & " already exists", vbExclamation
    Else
        oProps.Add strNewProp, vbNullString, ptString
        mfCancel = False
        Me.Hide
    End If
End Sub

